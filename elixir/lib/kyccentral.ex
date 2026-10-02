defmodule KYCCentral do
  @moduledoc """
  Official Elixir client for the [KYC Central](https://kyccentral.co.uk) API —
  UK company KYC and AML risk assessment.

      client = KYCCentral.new()                       # reads KYCCENTRAL_API_KEY
      {:ok, assessment} = KYCCentral.KYC.assess(client, "00445790")

      assessment.company_name  #=> "TESCO PLC"
      assessment.risk_level    #=> :medium

      for flag <- KYCCentral.Assessment.flags_at_or_above(assessment, :high) do
        IO.puts("\#{flag.code}: \#{flag.description}")
      end

  Every function returns `{:ok, result}` or `{:error, %KYCCentral.Error{}}`.

  ## Authentication

  Generate a key in [Account settings](https://kyccentral.co.uk/account) and set
  `KYCCENTRAL_API_KEY`, or pass `:api_key` to `new/1`.

  A key is not always required: reference and lookup endpoints work anonymously
  at a lower rate limit. Assessments and the AI endpoints always need one.

  ## The client struct

  `new/1` builds a plain struct holding configuration — it starts no processes
  and opens no connections, so there is nothing to supervise or close. Build one
  and pass it around, or memoise it in your application's config.

  ## Calling from Erlang

  Module names are prefixed with `Elixir.` from Erlang:

      Client = 'Elixir.KYCCentral':new([{api_key, <<"...">>}]),
      {ok, Assessment} = 'Elixir.KYCCentral.KYC':assess(Client, <<"00445790">>).
  """

  alias KYCCentral.Transport

  @default_base_url "https://api.kyccentral.co.uk"
  @default_receive_timeout 30_000
  @default_max_retries 2

  @api_key_env "KYCCENTRAL_API_KEY"
  @base_url_env "KYCCENTRAL_BASE_URL"

  @type t :: %__MODULE__{
          api_key: String.t() | nil,
          base_url: String.t(),
          receive_timeout: pos_integer(),
          max_retries: non_neg_integer(),
          headers: keyword() | map(),
          http: (map() -> {:ok, map()} | {:error, term()})
        }

  defstruct api_key: nil,
            base_url: @default_base_url,
            receive_timeout: @default_receive_timeout,
            max_retries: @default_max_retries,
            headers: [],
            http: &Transport.httpc_http/1

  @doc """
  Build a client.

  ## Options

    * `:api_key` — your API key. Defaults to the `KYCCENTRAL_API_KEY`
      environment variable, or `nil` for anonymous access.
    * `:base_url` — API root. Defaults to `KYCCENTRAL_BASE_URL`, then to
      production.
    * `:receive_timeout` — per-request timeout in milliseconds. Defaults to
      `#{@default_receive_timeout}`.
    * `:max_retries` — retries for timeouts, connection failures and retryable
      statuses (408, 429, 500, 502, 503, 504). Backoff is exponential with
      jitter and honours `Retry-After`. Defaults to `#{@default_max_retries}`;
      `0` disables retries.
    * `:headers` — extra headers on every request.
    * `:http` — a one-argument function used instead of the default
      `:httpc`-backed transport. Receives `%{method:, url:, headers:, body:, receive_timeout:}`
      and must return `{:ok, %{status:, headers:, body:}}` or `{:error, reason}`.
      Useful for tests, tracing, or plugging in a different HTTP stack.

  ## Examples

      KYCCentral.new()
      KYCCentral.new(api_key: "...", max_retries: 5)
      KYCCentral.new(base_url: "https://dev-api.kyccentral.co.uk")
  """
  @spec new(keyword()) :: t()
  def new(opts \\ []) do
    receive_timeout = Keyword.get(opts, :receive_timeout, @default_receive_timeout)
    max_retries = Keyword.get(opts, :max_retries, @default_max_retries)

    if not (is_integer(receive_timeout) and receive_timeout > 0) do
      raise ArgumentError, ":receive_timeout must be a positive integer"
    end

    if not (is_integer(max_retries) and max_retries >= 0) do
      raise ArgumentError, ":max_retries must be a non-negative integer"
    end

    %__MODULE__{
      api_key: opts |> Keyword.get(:api_key, System.get_env(@api_key_env)) |> presence(),
      base_url:
        opts
        |> Keyword.get(:base_url, System.get_env(@base_url_env) || @default_base_url)
        |> String.trim_trailing("/"),
      receive_timeout: receive_timeout,
      max_retries: max_retries,
      headers: Keyword.get(opts, :headers, []),
      http: Keyword.get(opts, :http, &Transport.httpc_http/1)
    }
  end

  @doc """
  Whether an API key was resolved. Anonymous clients hit lower rate limits.
  """
  @spec authenticated?(t()) :: boolean()
  def authenticated?(%__MODULE__{api_key: api_key}), do: not is_nil(api_key)

  @doc """
  Liveness and dependency status. Unversioned and unauthenticated.
  """
  @spec health(t()) :: {:ok, map()} | {:error, KYCCentral.Error.t()}
  def health(%__MODULE__{} = client) do
    Transport.request(client, :get, "/health", versioned: false)
  end

  @doc """
  Per-upstream availability: Companies House, FCA, GLEIF, sanctions and the rest.
  """
  @spec data_source_health(t()) :: {:ok, map()} | {:error, KYCCentral.Error.t()}
  def data_source_health(%__MODULE__{} = client) do
    Transport.request(client, :get, "/health/data-sources", versioned: false)
  end

  # An empty or whitespace-only key means "no key": it must not report the client
  # as authenticated while sending nothing useful.
  defp presence(nil), do: nil

  defp presence(value) when is_binary(value) do
    if String.trim(value) == "", do: nil, else: value
  end
end
