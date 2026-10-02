defmodule KYCCentral.Jobs do
  @moduledoc """
  Poll background jobs started by the API.

  You rarely need this directly — `KYCCentral.KYC.assess/3` polls for you.
  """

  import KYCCentral.Transport, only: [segment: 2]

  alias KYCCentral.{Error, Transport}

  @doc """
  Current state of a job: `%{"job_id" => ..., "status" => ..., "result" => ...}`.

  `status` is one of `"queued"`, `"running"`, `"done"` or `"error"`.
  """
  @spec get(KYCCentral.t(), String.t()) :: {:ok, map()} | {:error, Error.t()}
  def get(client, job_id) do
    with {:ok, id} <- segment(job_id, "job_id") do
      Transport.request(client, :get, "/jobs/#{id}")
    end
  end
end

defmodule KYCCentral.RuleSets do
  @moduledoc "Discover the rule sets available to your key."

  alias KYCCentral.{Error, Transport}

  @doc "Every rule set you can run: built-ins plus your workspace sets."
  @spec list(KYCCentral.t()) :: {:ok, [map()]} | {:error, Error.t()}
  def list(client), do: Transport.request(client, :get, "/rule-sets")
end

defmodule KYCCentral.Rules do
  @moduledoc "Discover individual rules and the company fields they can test."

  alias KYCCentral.{Error, Transport}

  @doc "Every rule, with its code, severity and rationale."
  @spec list(KYCCentral.t()) :: {:ok, [map()]} | {:error, Error.t()}
  def list(client), do: Transport.request(client, :get, "/rules")

  @doc "Company data fields exposed to configurable rule conditions."
  @spec fields(KYCCentral.t()) :: {:ok, term()} | {:error, Error.t()}
  def fields(client), do: Transport.request(client, :get, "/rules/fields")
end

defmodule KYCCentral.KYC do
  @moduledoc """
  The risk assessment endpoint — the reason this API exists.

  `assess/3` runs a rule set against one company and returns every risk flag it
  raised, alongside the evidence each rule was evaluated against.

  ## Queued assessments

  A cold assessment fans out to a dozen upstream sources and can take longer than
  a sensible HTTP timeout, so the API may accept the request with `202 Accepted`
  and a job id instead of holding the connection open. This module hides that: it
  polls the job to completion and returns the finished
  `t:KYCCentral.Assessment.t/0` either way. Pass `wait: false` to get the raw
  envelope back and drive the polling yourself.
  """

  alias KYCCentral.{Assessment, Error, Transport}

  @default_poll_interval 2_000
  @default_poll_timeout 180_000

  @queued_statuses ~w(queued running)

  @doc """
  Assess one company against a rule set.

  Pass a company number, or `q: "name"` to assess the top search result — but
  prefer the number, so you always know which entity you screened.

  **Requires an API key** on every plan. Free-plan keys are capped at a fixed
  number of assessments per calendar month; exceeding it returns a
  `%KYCCentral.Error{kind: :rate_limit}`. Cached results and failed runs do not
  consume quota.

  ## Options

    * `:q` — company name to search instead of passing a number. Mutually
      exclusive with `company_number`.
    * `:rule_set_id` — rule set slug. Defaults to the API's `"default"` set;
      see `KYCCentral.RuleSets.list/1`.
    * `:rule_code` — run a single rule instead of a whole set, e.g.
      `"ACCOUNTS_OVERDUE"`. Overrides `:rule_set_id`.
    * `:confirmed_media_urls` — adverse-media article URLs an analyst has
      already confirmed as genuine. Unconfirmed matches only ever raise a
      low-severity `ADVERSE_MEDIA_UNCONFIRMED` flag; listing a URL here promotes
      that article to its full severity.
    * `:confirmed_leak_ids` — ICIJ Offshore Leaks match ids, promoted the same way.
    * `:confirmed_psc_shareholder_links` — analyst-confirmed identity links, each
      formatted `"<psc name>||<shareholder name>"`.
    * `:wait` — poll a queued assessment to completion. Defaults to `true`.
    * `:poll_interval` — milliseconds between polls. Defaults to
      `#{@default_poll_interval}`.
    * `:poll_timeout` — give up waiting after this many milliseconds. Defaults
      to `#{@default_poll_timeout}`.

  ## Examples

      {:ok, assessment} = KYCCentral.KYC.assess(client, "00445790")
      {:ok, assessment} = KYCCentral.KYC.assess(client, q: "tesco plc")
      {:ok, assessment} = KYCCentral.KYC.assess(client, "00445790", rule_set_id: "quick")
  """
  @spec assess(KYCCentral.t(), String.t() | keyword(), keyword()) ::
          {:ok, Assessment.t() | map()} | {:error, Error.t()}
  def assess(client, company_number_or_opts, opts \\ [])

  def assess(client, opts, []) when is_list(opts) do
    do_assess(client, nil, opts)
  end

  def assess(client, company_number, opts) when is_binary(company_number) do
    do_assess(client, company_number, opts)
  end

  defp do_assess(client, company_number, opts) do
    with :ok <- validate_selector(company_number, opts[:q]),
         {:ok, payload} <- request_assessment(client, company_number, opts) do
      cond do
        not queued?(payload) -> {:ok, Assessment.from_map(payload)}
        opts[:wait] == false -> {:ok, payload}
        true -> await_job(client, to_string(payload["job_id"]), opts)
      end
    end
  end

  defp validate_selector(number, q) when is_binary(number) do
    if String.trim(number) == "" do
      validate_selector(nil, q)
    else
      validate_selector_pair(number, q)
    end
  end

  defp validate_selector(number, q), do: validate_selector_pair(number, q)

  defp validate_selector_pair(nil, nil) do
    {:error, Error.invalid_argument("Provide either a company number or :q.")}
  end

  defp validate_selector_pair(number, q) when is_binary(number) and is_binary(q) do
    {:error, Error.invalid_argument("Provide either a company number or :q, not both.")}
  end

  defp validate_selector_pair(_number, _q), do: :ok

  defp request_assessment(client, company_number, opts) do
    params = [
      company_number: company_number,
      q: opts[:q],
      rule_set_id: opts[:rule_set_id],
      rule_code: opts[:rule_code],
      confirmed_media_url: opts[:confirmed_media_urls],
      confirmed_leak_id: opts[:confirmed_leak_ids],
      confirmed_psc_shareholder_link: opts[:confirmed_psc_shareholder_links]
    ]

    Transport.request(client, :get, "/kyc/assess", params: params)
  end

  # The API answers a queued assessment with a job envelope rather than a result.
  defp queued?(payload) when is_map(payload) do
    Map.has_key?(payload, "job_id") and not Map.has_key?(payload, "company_number")
  end

  defp queued?(_), do: false

  defp await_job(client, job_id, opts) do
    interval = Keyword.get(opts, :poll_interval, @default_poll_interval)
    timeout = Keyword.get(opts, :poll_timeout, @default_poll_timeout)
    deadline = System.monotonic_time(:millisecond) + timeout

    poll(client, job_id, interval, timeout, deadline)
  end

  defp poll(client, job_id, interval, timeout, deadline) do
    with {:ok, state} <- KYCCentral.Jobs.get(client, job_id),
         :pending <- job_outcome(state, job_id) do
      wait_and_retry(client, job_id, interval, timeout, deadline)
    else
      {:ok, result} -> {:ok, Assessment.from_map(result)}
      {:error, _reason} = error -> error
    end
  end

  defp wait_and_retry(client, job_id, interval, timeout, deadline) do
    if System.monotonic_time(:millisecond) + interval > deadline do
      {:error,
       %Error{
         kind: :job_timeout,
         job_id: job_id,
         message:
           "Assessment job #{job_id} did not finish within #{timeout}ms. It may still " <>
             "complete — re-running the same request will return the cached result once it does."
       }}
    else
      if interval > 0, do: Process.sleep(interval)
      poll(client, job_id, interval, timeout, deadline)
    end
  end

  defp job_outcome(%{"status" => status}, _job_id) when status in @queued_statuses, do: :pending

  defp job_outcome(%{"status" => "done", "result" => result}, _job_id) when is_map(result) do
    {:ok, result}
  end

  defp job_outcome(%{"status" => "done"}, job_id) do
    {:error,
     %Error{
       kind: :job_failed,
       job_id: job_id,
       message: "The assessment finished but its result was no longer available — please re-run."
     }}
  end

  defp job_outcome(%{"status" => "error"} = state, job_id) do
    {:error,
     %Error{
       kind: :job_failed,
       job_id: job_id,
       message: state["error"] || "The assessment job failed."
     }}
  end

  defp job_outcome(state, job_id) do
    {:error,
     %Error{
       kind: :job_failed,
       job_id: job_id,
       message: "Unexpected job status #{inspect(Map.get(state, "status"))}."
     }}
  end
end
