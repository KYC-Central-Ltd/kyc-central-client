defmodule KYCCentral.Error do
  @moduledoc """
  The single error type returned by every function in this library.

  Rather than a tree of exception modules, failures carry a `:kind` atom, which
  makes them pleasant to match on:

      case KYCCentral.KYC.assess(client, "00445790") do
        {:ok, assessment} -> assessment
        {:error, %KYCCentral.Error{kind: :not_found}} -> :no_such_company
        {:error, %KYCCentral.Error{kind: :rate_limit, retry_after: seconds}} -> {:wait, seconds}
        {:error, error} -> raise error
      end

  This is also an exception, so `raise error` works when you would rather not
  handle a failure locally.
  """

  @typedoc """
  What went wrong.

  Transport failures:

    * `:connection` — the request never produced a response.
    * `:timeout` — the request timed out.

  API responses:

    * `:bad_request` (400) — the request was malformed.
    * `:authentication` (401) — no API key was sent, or it is not valid.
    * `:permission_denied` (403) — the plan does not include this endpoint;
      usually an active Professional subscription is required.
    * `:not_found` (404) — no such company, officer, charge or filing.
    * `:unprocessable_entity` (422) — failed the API's validation rules.
    * `:rate_limit` (429) — a rate limit or plan quota was exceeded.
    * `:server_error` (5xx) — the API failed to handle a valid request.
    * `:service_unavailable` (503) — a dependency the API needs is down. Like
      `:rate_limit`, it carries `:retry_after` when the API sends `Retry-After`.
    * `:unexpected_status` — any other non-2xx status.

  Queued assessments:

    * `:job_failed` — the API reported the queued assessment as failed.
    * `:job_timeout` — the assessment did not finish within `:poll_timeout`.

  Caller mistakes, detected before any request is made:

    * `:invalid_argument`
  """
  @type kind ::
          :connection
          | :timeout
          | :bad_request
          | :authentication
          | :permission_denied
          | :not_found
          | :unprocessable_entity
          | :rate_limit
          | :server_error
          | :service_unavailable
          | :unexpected_status
          | :job_failed
          | :job_timeout
          | :invalid_argument

  @type t :: %__MODULE__{
          kind: kind(),
          message: String.t(),
          status: pos_integer() | nil,
          detail: String.t() | nil,
          body: term(),
          headers: map(),
          retry_after: number() | nil,
          job_id: String.t() | nil,
          reason: term()
        }

  defexception [
    :kind,
    :message,
    :status,
    :detail,
    :body,
    :retry_after,
    :job_id,
    :reason,
    headers: %{}
  ]

  @status_kinds %{
    400 => :bad_request,
    401 => :authentication,
    403 => :permission_denied,
    404 => :not_found,
    422 => :unprocessable_entity,
    429 => :rate_limit,
    503 => :service_unavailable
  }

  @doc false
  @spec invalid_argument(String.t()) :: t()
  def invalid_argument(message) do
    %__MODULE__{kind: :invalid_argument, message: message}
  end

  @doc false
  @spec from_response(pos_integer(), term(), map(), String.t(), String.t()) :: t()
  def from_response(status, body, headers, method, url) do
    detail = extract_detail(body, "HTTP #{status}")

    %__MODULE__{
      kind: kind_for_status(status),
      message: "#{method} #{url} failed with #{status}: #{detail}",
      status: status,
      detail: detail,
      body: body,
      headers: headers,
      retry_after: if(status in [429, 503], do: retry_after(headers))
    }
  end

  defp kind_for_status(status) do
    case Map.fetch(@status_kinds, status) do
      {:ok, kind} -> kind
      :error -> if status >= 500, do: :server_error, else: :unexpected_status
    end
  end

  @doc """
  Read `Retry-After` out of a response's headers, in seconds.

  Returns `nil` when the header is absent or not a number.
  """
  @spec retry_after(map()) :: number() | nil
  def retry_after(headers) do
    case header(headers, "retry-after") do
      nil ->
        nil

      value ->
        case Float.parse(value) do
          {seconds, _rest} -> seconds
          :error -> nil
        end
    end
  end

  @doc """
  Fetch one header value, case-insensitively.

  Accepts the map-of-lists shape Req returns as well as a plain list of tuples,
  so an injected HTTP function can use either.
  """
  @spec header(map() | list(), String.t()) :: String.t() | nil
  def header(headers, name) when is_map(headers) do
    wanted = String.downcase(name)

    Enum.find_value(headers, fn {key, value} ->
      if String.downcase(to_string(key)) == wanted, do: first_value(value)
    end)
  end

  def header(headers, name) when is_list(headers) do
    headers |> Map.new() |> header(name)
  end

  defp first_value([value | _]), do: to_string(value)
  defp first_value([]), do: nil
  defp first_value(value), do: to_string(value)

  # The API returns `{"detail": "..."}` for handled errors, and FastAPI's
  # `{"detail": [{loc, msg}, ...]}` list form for validation failures.
  defp extract_detail(%{"detail" => detail}, _fallback) when is_binary(detail), do: detail

  defp extract_detail(%{"detail" => entries}, _fallback)
       when is_list(entries) and entries != [] do
    Enum.map_join(entries, "; ", &format_validation_entry/1)
  end

  defp extract_detail(_body, fallback), do: fallback

  defp format_validation_entry(%{"msg" => msg} = entry) do
    case entry |> Map.get("loc", []) |> Enum.reject(&(&1 == "body")) |> Enum.join(".") do
      "" -> to_string(msg)
      location -> "#{location}: #{msg}"
    end
  end

  defp format_validation_entry(entry), do: inspect(entry)
end
