defmodule KYCCentral.Stub do
  @moduledoc """
  A stub HTTP function for tests.

  Every test runs against this rather than the network, so the suite is offline
  and needs no API key. Requests are recorded so tests can assert on the URL,
  headers and body that would have gone out.
  """

  @base_url "https://api.test.invalid"

  @doc "The base URL every stubbed client uses."
  def base_url, do: @base_url

  @doc """
  Build a client whose HTTP function replays `responses` in order.

  Once the list is exhausted the last response repeats, which keeps polling
  tests short. Each response is `{status, body}` or `{status, body, headers}`.
  """
  def client(responses, opts \\ []) do
    {:ok, agent} = Agent.start_link(fn -> %{responses: List.wrap(responses), calls: []} end)

    http = fn request ->
      Agent.get_and_update(agent, fn state ->
        {response, remaining} = next(state.responses)
        {{:ok, response}, %{state | responses: remaining, calls: state.calls ++ [request]}}
      end)
    end

    client =
      KYCCentral.new(
        Keyword.merge(
          [api_key: "test-key", base_url: @base_url, http: http, max_retries: 0],
          opts
        )
      )

    {client, agent}
  end

  @doc "A client that always fails the transport with `reason`."
  def failing_client(reason, opts \\ []) do
    {:ok, agent} = Agent.start_link(fn -> %{responses: [], calls: []} end)

    http = fn request ->
      Agent.update(agent, fn state -> %{state | calls: state.calls ++ [request]} end)
      {:error, reason}
    end

    client =
      KYCCentral.new(Keyword.merge([api_key: "test-key", base_url: @base_url, http: http], opts))

    {client, agent}
  end

  @doc """
  Build a client that replays `steps` in order, each either `{:error, reason}`
  (a transport failure) or a response tuple as accepted by `client/2`. The last
  step repeats once the list is exhausted.
  """
  def sequence_client(steps, opts \\ []) do
    {:ok, agent} = Agent.start_link(fn -> %{responses: steps, calls: []} end)

    http = fn request ->
      Agent.get_and_update(agent, fn state ->
        {result, remaining} = next_step(state.responses)

        {result, %{state | responses: remaining, calls: state.calls ++ [request]}}
      end)
    end

    client =
      KYCCentral.new(Keyword.merge([api_key: "test-key", base_url: @base_url, http: http], opts))

    {client, agent}
  end

  @doc "Every request the stub has received, oldest first."
  def calls(agent), do: Agent.get(agent, & &1.calls)

  @doc "The nth request (zero-based)."
  def call(agent, index \\ 0), do: agent |> calls() |> Enum.at(index)

  @doc "How many requests the stub has received."
  def call_count(agent), do: agent |> calls() |> length()

  @doc "The path of the nth request, without the query string."
  def path(agent, index \\ 0) do
    agent |> call(index) |> Map.fetch!(:url) |> URI.parse() |> Map.get(:path)
  end

  @doc "The decoded query parameters of the nth request, as a list of pairs."
  def query(agent, index \\ 0) do
    agent
    |> call(index)
    |> Map.fetch!(:url)
    |> URI.parse()
    |> Map.get(:query)
    |> case do
      nil -> []
      query -> URI.query_decoder(query) |> Enum.to_list()
    end
  end

  @doc "All values sent for one repeatable query parameter."
  def query_values(agent, key, index \\ 0) do
    agent |> query(index) |> Enum.filter(&(elem(&1, 0) == key)) |> Enum.map(&elem(&1, 1))
  end

  @doc "A single query parameter value, or nil."
  def query_value(agent, key, index \\ 0) do
    agent |> query_values(key, index) |> List.first()
  end

  @doc "The decoded JSON body of the nth request."
  def body(agent, index \\ 0) do
    case call(agent, index) do
      %{body: nil} -> nil
      %{body: raw} -> Jason.decode!(raw)
    end
  end

  @doc "One request header value, case-insensitively."
  def header(agent, name, index \\ 0) do
    agent |> call(index) |> Map.fetch!(:headers) |> KYCCentral.Error.header(name)
  end

  @doc "A JSON response tuple."
  def json(body, status \\ 200) do
    {status, Jason.encode!(body), %{"content-type" => ["application/json"]}}
  end

  @doc "A minimal but realistic `/v1/kyc/assess` body."
  def assessment_payload do
    %{
      "company_number" => "00445790",
      "company_name" => "TESCO PLC",
      "risk_level" => "medium",
      "checked_at" => "2026-08-13T10:00:00+00:00",
      "data_fetched_at" => "2026-08-13T09:55:00+00:00",
      "flags" => [
        %{
          "code" => "ACCOUNTS_OVERDUE",
          "severity" => "high",
          "description" => "Annual accounts are 42 days overdue."
        },
        %{
          "code" => "ADVERSE_MEDIA_UNCONFIRMED",
          "severity" => "low",
          "description" => "3 possible adverse media matches require review."
        }
      ],
      "profile" => %{"company_status" => "active"},
      "officers_summary" => %{"total" => 12},
      "psc_summary" => %{"total" => 3},
      "psc_chain_depth" => 2,
      "rule_results" => [
        %{
          "code" => "ACCOUNTS_OVERDUE",
          "name" => "Accounts overdue",
          "description" => "Checks whether annual accounts are past their due date.",
          "severity" => "high",
          "status" => "failed",
          "reason" => "Annual accounts are 42 days overdue."
        },
        %{
          "code" => "COMPANY_NOT_ACTIVE",
          "name" => "Company not active",
          "description" => "Checks the company is trading.",
          "severity" => "critical",
          "status" => "passed",
          "reason" => nil
        }
      ],
      "timed_out_services" => [],
      "failed_rules" => [],
      "pending_extractions" => []
    }
  end

  defp next_step([last]), do: {step_result(last), [last]}
  defp next_step([head | tail]), do: {step_result(head), tail}

  defp step_result({:error, _reason} = error), do: error
  defp step_result(response), do: {:ok, normalise(response)}

  defp next([]), do: {%{status: 200, headers: %{}, body: nil}, []}

  defp next([last]), do: {normalise(last), [last]}

  defp next([head | tail]), do: {normalise(head), tail}

  defp normalise({status, body}), do: %{status: status, headers: %{}, body: body}

  defp normalise({status, body, headers}),
    do: %{status: status, headers: headers, body: body}
end
