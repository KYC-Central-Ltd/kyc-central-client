defmodule KYCCentral.Reports do
  @moduledoc """
  The full report as JSON rather than a PDF. **Requires an API key.**
  """

  alias KYCCentral.{Error, Transport}

  @doc """
  The full report — the assessment, flags per rule set and every section's data —
  as JSON instead of a PDF.

  Requires an API key and uses one PDF report credit (a subscriber's monthly
  allowance first, then purchased credits).

  A report is never returned with a required check missing: that is a 503 with
  `Retry-After` (about five minutes) and the credit is returned. The client does
  not retry it; wait for the error's `:retry_after` and call again.

  ## Options

    * `:sections` — any of `assessment`, `company_data`, `filings`,
      `disqualifications`, `fca`, `gleif`, `individual_insolvency`,
      `confirmation_statements`, `sanctions`, `adverse_media`, `ai_analysis`,
      `offshore_leaks`. Defaults to `assessment`, `company_data`, `sanctions`.
      Leave out `ai_analysis` for a report with no AI-written content. A list of
      strings is sent comma-joined; a binary is sent unchanged.
    * `:rule_set_ids` — rule sets to run; their rules are combined and
      deduplicated. A list of strings is sent comma-joined; a binary is sent
      unchanged.
    * `:ai_provider` — override the AI provider.
    * `:fca_frn` — a confirmed FCA firm reference number. Once given, the FCA
      lookup becomes a required check.
    * `:context` — a map of the analyst's confirmations, sent as-is. Its
      `accepted_gaps` (with `accepted_gaps_at`, no more than 24 hours old) lists
      `sanctions` / `adverse_media` / `offshore_leaks` checks to proceed without
      if they are unavailable; those come back under `generated_without`.
    * `:receive_timeout` — timeout in milliseconds for this call. Defaults to 120
      seconds, or the client's `:receive_timeout` if that is longer. Must be a
      positive integer.
  """
  @spec data(KYCCentral.t(), String.t(), keyword()) :: {:ok, map()} | {:error, Error.t()}
  def data(client, company_number, opts \\ []) do
    with {:ok, timeout} <- Transport.ai_receive_timeout(client, opts) do
      body =
        %{"company_number" => company_number}
        |> put_optional("sections", comma_joined(opts[:sections]))
        |> put_optional("rule_set_ids", comma_joined(opts[:rule_set_ids]))
        |> put_optional("ai_provider", opts[:ai_provider])
        |> put_optional("fca_frn", opts[:fca_frn])
        |> put_optional("context", opts[:context])

      Transport.request(client, :post, "/billing/report-data",
        body: body,
        receive_timeout: timeout
      )
    end
  end

  # A list becomes one comma-joined string; a binary passes through; an empty
  # list counts as not given.
  defp comma_joined(nil), do: nil
  defp comma_joined([]), do: nil
  defp comma_joined(value) when is_binary(value), do: value
  defp comma_joined(values) when is_list(values), do: Enum.join(values, ",")

  defp put_optional(body, _key, nil), do: body
  defp put_optional(body, key, value), do: Map.put(body, key, value)
end
