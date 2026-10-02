defmodule KYCCentral.Transport do
  @moduledoc """
  HTTP plumbing: URL building, retries, decoding and error mapping.

  Internal. The public surface is `KYCCentral` and the resource modules.
  """

  alias KYCCentral.Error

  @retryable_statuses [408, 429, 500, 502, 503, 504]
  @initial_backoff_ms 500
  @max_backoff_ms 8_000
  @ai_receive_timeout 120_000

  @doc """
  Issue a request, retrying transient failures.

  Returns the decoded body on success, or `{:error, %KYCCentral.Error{}}`.

  GETs retry timeouts, connection failures and 408/429/5xx. POSTs may invoke a
  billed LLM call, so they are retried only when the request certainly never
  reached the server (the connection could not be established, and it was not a
  timeout) or when the API answers 429/503 with `Retry-After`.

  `:receive_timeout` in `opts` replaces the client's timeout for this request.
  """
  @spec request(KYCCentral.t(), :get | :post, String.t(), keyword()) ::
          {:ok, term()} | {:error, Error.t()}
  def request(%KYCCentral{} = client, method, path, opts \\ []) do
    url = build_url(client, path, opts[:params], Keyword.get(opts, :versioned, true))
    timeout = Keyword.get(opts, :receive_timeout, client.receive_timeout)
    attempt(client, method, url, opts[:body], timeout, 0)
  end

  @doc false
  @spec ai_receive_timeout(KYCCentral.t(), keyword()) ::
          {:ok, pos_integer()} | {:error, Error.t()}
  def ai_receive_timeout(client, opts) do
    case Keyword.fetch(opts, :receive_timeout) do
      :error ->
        {:ok, max(client.receive_timeout, @ai_receive_timeout)}

      {:ok, timeout} when is_integer(timeout) and timeout > 0 ->
        {:ok, timeout}

      {:ok, other} ->
        {:error,
         Error.invalid_argument(
           ":receive_timeout must be a positive integer (milliseconds), got #{inspect(other)}"
         )}
    end
  end

  defp attempt(client, method, url, body, timeout, retries) do
    verb = method |> to_string() |> String.upcase()

    case perform(client, method, url, body, timeout) do
      {:ok, %{status: status} = response} when status in @retryable_statuses ->
        if retries < client.max_retries and retry_status?(method, response) and
             not long_retry_after?(response) do
          response |> retry_delay(retries) |> sleep()
          attempt(client, method, url, body, timeout, retries + 1)
        else
          finish(response, verb, url)
        end

      {:ok, response} ->
        finish(response, verb, url)

      {:error, reason} ->
        if retries < client.max_retries and retry_error?(method, reason) do
          sleep(retry_delay(nil, retries))
          attempt(client, method, url, body, timeout, retries + 1)
        else
          {:error, transport_error(reason, verb, url)}
        end
    end
  end

  # A POST may already be running server-side (a billed LLM call), so it is only
  # retried when the server has said "not processed, come back later".
  defp retry_status?(:post, %{status: status, headers: headers}) do
    status in [429, 503] and Error.header(headers, "retry-after") != nil
  end

  defp retry_status?(_method, _response), do: true

  # A POST is only retried when the connection was certainly never established.
  defp retry_error?(:post, {:failed_connect, details}) when is_list(details),
    do: not nested_timeout?(details)

  defp retry_error?(:post, _reason), do: false
  defp retry_error?(_method, _reason), do: true

  defp perform(client, method, url, body, timeout) do
    request = %{
      method: method,
      url: url,
      headers: headers(client, body != nil),
      body: if(body, do: Jason.encode!(body)),
      receive_timeout: timeout
    }

    client.http.(request)
  end

  @doc """
  The default HTTP function, backed by OTP's own `:httpc`.

  Using `:httpc` is what lets this library ship with Jason as its only runtime
  dependency — adding it to a project pulls in no HTTP stack. Pass `:http` to
  `KYCCentral.new/1` to use Req, Finch, Tesla or anything else instead.

  Retries are handled by this module rather than the transport, so the policy
  matches the Python and JavaScript clients. Bodies are returned undecoded and
  decoded centrally, so an injected function and the default behave identically.
  """
  @spec httpc_http(map()) :: {:ok, map()} | {:error, term()}
  def httpc_http(request) do
    {:ok, _started} = Application.ensure_all_started(:inets)
    {:ok, _started} = Application.ensure_all_started(:ssl)

    url = String.to_charlist(request.url)

    http_options = httpc_options(request)

    options = [body_format: :binary]

    result =
      case request.method do
        :get ->
          :httpc.request(:get, {url, charlist_headers(request.headers)}, http_options, options)

        :post ->
          # httpc takes the content type as its own argument and rejects a
          # duplicate in the header list, so it is filtered out here.
          headers = Enum.reject(request.headers, &(elem(&1, 0) == "content-type"))

          :httpc.request(
            :post,
            {url, charlist_headers(headers), ~c"application/json", request.body || ""},
            http_options,
            options
          )
      end

    case result do
      {:ok, {{_version, status, _reason}, headers, body}} ->
        {:ok, %{status: status, headers: decode_headers(headers), body: body}}

      {:error, reason} ->
        {:error, reason}
    end
  end

  @doc false
  @spec httpc_options(map()) :: keyword()
  def httpc_options(request) do
    [
      timeout: request.receive_timeout,
      connect_timeout: request.receive_timeout,
      # `:httpc` autoredirects GETs by default. The API key travels in the
      # custom `X-API-Key` header, which `:httpc` would forward to whatever
      # host a redirect names, so redirects are never followed: a 3xx comes
      # back as an ordinary status error carrying the `location` header.
      autoredirect: false,
      ssl: ssl_options()
    ]
  end

  # `:httpc` does not verify certificates unless told to, and a client that
  # carries an API key must never talk to an unverified peer. `cacerts_get/0`
  # uses the OS trust store (OTP 25+).
  defp ssl_options do
    [
      verify: :verify_peer,
      cacerts: :public_key.cacerts_get(),
      depth: 3,
      customize_hostname_check: [
        match_fun: :public_key.pkix_verify_hostname_match_fun(:https)
      ],
      versions: [:"tlsv1.2", :"tlsv1.3"]
    ]
  end

  defp charlist_headers(headers) do
    Enum.map(headers, fn {key, value} ->
      {String.to_charlist(to_string(key)), String.to_charlist(to_string(value))}
    end)
  end

  defp decode_headers(headers) do
    Map.new(headers, fn {key, value} -> {to_string(key), to_string(value)} end)
  end

  defp headers(client, has_body?) do
    base = [{"accept", "application/json"}, {"user-agent", user_agent()}]
    base = if has_body?, do: [{"content-type", "application/json"} | base], else: base
    base = if client.api_key, do: [{"x-api-key", client.api_key} | base], else: base
    base ++ Enum.map(client.headers, fn {key, value} -> {to_string(key), to_string(value)} end)
  end

  defp user_agent do
    version = Application.spec(:kyccentral, :vsn) || ~c"dev"
    "kyccentral-elixir/#{version} (elixir/#{System.version()}; otp/#{System.otp_release()})"
  end

  defp finish(%{status: status, headers: headers, body: body}, verb, url) do
    decoded = decode(body, headers)

    if status in 200..299 do
      {:ok, decoded}
    else
      {:error, Error.from_response(status, decoded, normalise_headers(headers), verb, url)}
    end
  end

  # Tolerates empty and non-JSON payloads, and accepts an already-decoded body so
  # a test stub can hand back a map directly.
  defp decode(body, _headers) when is_map(body) or is_list(body), do: body
  defp decode(nil, _headers), do: nil
  defp decode("", _headers), do: nil

  defp decode(body, headers) when is_binary(body) do
    content_type = Error.header(headers, "content-type") || ""

    if String.contains?(content_type, "json") do
      case Jason.decode(body) do
        {:ok, decoded} -> decoded
        {:error, _} -> body
      end
    else
      body
    end
  end

  defp decode(body, _headers), do: body

  defp normalise_headers(headers) when is_map(headers), do: headers
  defp normalise_headers(headers) when is_list(headers), do: Map.new(headers)
  defp normalise_headers(_), do: %{}

  defp transport_error(reason, verb, url) do
    if timeout?(reason) do
      %Error{
        kind: :timeout,
        message: "#{verb} #{url} timed out.",
        reason: reason
      }
    else
      %Error{
        kind: :connection,
        message: "#{verb} #{url} failed: #{describe(reason)}",
        reason: reason
      }
    end
  end

  defp timeout?(:timeout), do: true
  defp timeout?({:failed_connect, details}) when is_list(details), do: nested_timeout?(details)
  defp timeout?(%{reason: :timeout}), do: true
  defp timeout?(_), do: false

  # `:httpc` reports a connect timeout as
  # `{:failed_connect, [{:to_address, _}, {:inet, [:inet], :timeout}]}`.
  defp nested_timeout?(details) do
    Enum.any?(details, fn
      {_transport, _options, :timeout} -> true
      {_key, :timeout} -> true
      _ -> false
    end)
  end

  defp describe(%{__exception__: true} = exception), do: Exception.message(exception)
  defp describe(reason), do: inspect(reason)

  # Honours `Retry-After` when the API sends one (it does on 429), otherwise backs
  # off exponentially with full jitter, so a fleet recovering from one outage does
  # not retry in lockstep. Long `Retry-After` values (exceeding max backoff) are not
  # waited out; the error is returned to the caller instead.
  defp retry_delay(%{headers: headers}, attempt) do
    case Error.retry_after(headers) do
      nil -> jittered_backoff(attempt)
      seconds -> seconds |> Kernel.*(1000) |> round() |> min(@max_backoff_ms) |> max(0)
    end
  end

  defp retry_delay(nil, attempt), do: jittered_backoff(attempt)

  defp jittered_backoff(attempt) do
    ceiling = min(@initial_backoff_ms * 2 ** attempt, @max_backoff_ms)
    round(ceiling / 2 + :rand.uniform() * (ceiling / 2))
  end

  # Check if a response has a `Retry-After` header longer than the max backoff.
  # If so, the caller should not retry but instead get the error immediately,
  # so they can schedule the retry themselves.
  defp long_retry_after?(%{headers: headers}) do
    case Error.retry_after(headers) do
      nil -> false
      seconds -> seconds * 1000 > @max_backoff_ms
    end
  end

  defp sleep(0), do: :ok
  defp sleep(milliseconds), do: Process.sleep(milliseconds)

  @doc false
  @spec build_url(KYCCentral.t(), String.t(), keyword() | nil, boolean()) :: String.t()
  def build_url(client, path, params, versioned?) do
    prefix = if versioned?, do: "/v1", else: ""
    path = if String.starts_with?(path, "/"), do: path, else: "/" <> path
    client.base_url <> prefix <> path <> query_string(params)
  end

  @doc """
  Encode query parameters, dropping unset ones and repeating list values.

  Built by hand rather than through `URI.encode_query/1` because several
  endpoints take repeatable parameters (`confirmed_media_url`, `company_status`),
  which need `?k=a&k=b` rather than one comma-joined value.
  """
  @spec query_string(keyword() | nil) :: String.t()
  def query_string(nil), do: ""
  def query_string([]), do: ""

  def query_string(params) do
    case Enum.flat_map(params, &encode_param/1) do
      [] -> ""
      pairs -> "?" <> Enum.join(pairs, "&")
    end
  end

  # `nil` means "caller did not supply this" and must never be sent as the
  # literal string "nil".
  defp encode_param({_key, nil}), do: []
  defp encode_param({_key, []}), do: []

  defp encode_param({key, values}) when is_list(values) do
    values |> Enum.reject(&is_nil/1) |> Enum.map(&pair(key, &1))
  end

  defp encode_param({key, value}), do: [pair(key, value)]

  defp pair(key, value) do
    "#{URI.encode_www_form(to_string(key))}=#{URI.encode_www_form(to_string(value))}"
  end

  @doc """
  Validate and percent-encode a value being interpolated into a URL path.

  Empty segments would silently collapse the path onto a different endpoint, and
  officer ids are opaque upstream tokens, so both are checked and encoded.
  """
  @spec segment(term(), String.t()) :: {:ok, String.t()} | {:error, Error.t()}
  def segment(value, name) when is_binary(value) do
    case String.trim(value) do
      "" -> {:error, Error.invalid_argument("#{name} must be a non-empty string")}
      trimmed -> {:ok, URI.encode_www_form(trimmed)}
    end
  end

  def segment(_value, name) do
    {:error, Error.invalid_argument("#{name} must be a non-empty string")}
  end

  @doc """
  Build the `%{"names" => [...]}` body used by the batch screening endpoints.
  """
  @spec names_body([String.t()], pos_integer() | nil) :: {:ok, map()} | {:error, Error.t()}
  def names_body(names, limit \\ nil) when is_list(names) do
    cleaned =
      names
      |> Enum.map(&(&1 |> to_string() |> String.trim()))
      |> Enum.reject(&(&1 == ""))

    cond do
      cleaned == [] ->
        {:error, Error.invalid_argument("names must contain at least one non-empty string")}

      limit && length(cleaned) > limit ->
        {:error,
         Error.invalid_argument("names accepts at most #{limit} entries, got #{length(cleaned)}")}

      true ->
        {:ok, %{"names" => cleaned}}
    end
  end
end
