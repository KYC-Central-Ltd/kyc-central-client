defmodule KYCCentral.Analysis do
  @moduledoc """
  LLM-written analyst commentary over an assessment.

  **Requires an active Professional subscription**, except for `status/1`. These
  calls invoke a language model, so they are slower and dearer than the
  deterministic rule engine — and, like any LLM output, the narrative is a
  drafting aid for an analyst, not a compliance decision.
  """

  alias KYCCentral.{Error, Transport}

  @type result :: {:ok, map()} | {:error, Error.t()}

  @filing_extract_modes ~w(extract verify)
  @max_sections 50

  @doc "Which AI providers are configured. Available without a subscription."
  @spec status(KYCCentral.t()) :: result()
  def status(client), do: Transport.request(client, :get, "/analysis/status")

  @doc """
  Write a narrative risk analysis for one company.

  ## Options

    * `:rule_set_id` — rule set whose findings should frame the analysis.
    * `:provider` — override the AI provider, e.g. `"claude"`, `"gpt"`,
      `"gemini"`. Defaults to whichever the API is configured with.
    * `:sections` — restrict the write-up to named sections. At most
      #{@max_sections}.
    * `:fca_frn` — FCA Firm Reference Number, when the company is regulated and
      you already know it.
    * `:context` — evidence gathered elsewhere (confirmed screening hits,
      selected filings, analyst-confirmed identity links) folded into the prompt,
      so the analysis reflects your review rather than raw unconfirmed matches.
    * `:receive_timeout` — timeout in milliseconds for this call. Defaults to 120
      seconds, or the client's `:receive_timeout` if that is longer. Must be a
      positive integer.
  """
  @spec company(KYCCentral.t(), String.t(), keyword()) :: result()
  def company(client, company_number, opts \\ []) do
    with {:ok, sections} <- validate_sections(opts[:sections]),
         {:ok, timeout} <- Transport.ai_receive_timeout(client, opts) do
      body =
        %{"company_number" => company_number}
        |> put_optional("rule_set_id", opts[:rule_set_id])
        |> put_optional("provider", opts[:provider])
        |> put_optional("sections", sections)
        |> put_optional("fca_frn", opts[:fca_frn])
        |> put_optional("context", opts[:context])

      Transport.request(client, :post, "/analysis/company", body: body, receive_timeout: timeout)
    end
  end

  @doc """
  Summarise adverse media results into a short overview.

  ## Options

    * `:provider`
    * `:results` — search results to summarise, as returned by
      `KYCCentral.News.screen_company/2` or `KYCCentral.News.search_names/2`.
    * `:receive_timeout` — timeout in milliseconds for this call. Defaults to 120
      seconds, or the client's `:receive_timeout` if that is longer. Must be a
      positive integer.
  """
  @spec adverse_media_overview(KYCCentral.t(), String.t(), keyword()) :: result()
  def adverse_media_overview(client, company_number, opts \\ []) do
    with {:ok, timeout} <- Transport.ai_receive_timeout(client, opts) do
      body =
        %{"company_number" => company_number}
        |> put_optional("provider", opts[:provider])
        |> put_optional("results", opts[:results])

      Transport.request(client, :post, "/analysis/adverse-media-overview",
        body: body,
        receive_timeout: timeout
      )
    end
  end

  @doc """
  Read a filing PDF with an LLM.

  ## Options

    * `:mode` — `"extract"` to pull structured data out of the filing, or
      `"verify"` to check an existing extraction against the document. Defaults
      to `"extract"`.
    * `:provider`
    * `:receive_timeout` — timeout in milliseconds for this call. Defaults to 120
      seconds, or the client's `:receive_timeout` if that is longer. Must be a
      positive integer.
  """
  @spec filing_extract(KYCCentral.t(), String.t(), String.t(), keyword()) :: result()
  def filing_extract(client, company_number, transaction_id, opts \\ []) do
    mode = Keyword.get(opts, :mode, "extract")

    with {:ok, timeout} <- Transport.ai_receive_timeout(client, opts),
         :ok <- validate_mode(mode) do
      body =
        %{
          "company_number" => company_number,
          "transaction_id" => transaction_id,
          "mode" => mode
        }
        |> put_optional("provider", opts[:provider])

      Transport.request(client, :post, "/analysis/filing-extract",
        body: body,
        receive_timeout: timeout
      )
    end
  end

  @doc """
  Read a charge's "Registration of a charge" form with a vision-capable LLM, for
  forms with no text layer (paper and pre-2013 filings) — the case
  `KYCCentral.Companies.extract_charge_registration/3` answers with `needs_ai`.

  Returns the same merged record, with source `"ai_vision"`; an unreadable form
  returns `%{"available" => false, "reason" => ...}`. Spends AI credits on first
  use; a repeat call for the same charge is served from the stored record.

  A blank `charge_key` returns an `:invalid_argument` error without making a
  request. The key is sent trimmed.

  ## Options

    * `:provider`
    * `:receive_timeout` — timeout in milliseconds for this call. Defaults to 120
      seconds, or the client's `:receive_timeout` if that is longer. Must be a
      positive integer.
  """
  @spec charge_registration(KYCCentral.t(), String.t(), String.t(), keyword()) :: result()
  def charge_registration(client, company_number, charge_key, opts \\ []) do
    with {:ok, key} <- Transport.charge_key(charge_key),
         {:ok, timeout} <- Transport.ai_receive_timeout(client, opts) do
      body =
        %{"company_number" => company_number, "charge_key" => key}
        |> put_optional("provider", opts[:provider])

      Transport.request(client, :post, "/analysis/charge-registration",
        body: body,
        receive_timeout: timeout
      )
    end
  end

  defp validate_mode(mode) when mode in @filing_extract_modes, do: :ok

  defp validate_mode(mode) do
    {:error,
     Error.invalid_argument(
       ":mode must be one of #{Enum.join(@filing_extract_modes, ", ")}, got #{inspect(mode)}"
     )}
  end

  defp validate_sections(nil), do: {:ok, nil}
  defp validate_sections([]), do: {:ok, nil}

  defp validate_sections(sections) when is_list(sections) do
    if length(sections) > @max_sections do
      {:error,
       Error.invalid_argument(
         ":sections accepts at most #{@max_sections} entries, got #{length(sections)}"
       )}
    else
      {:ok, sections}
    end
  end

  defp validate_sections(other) do
    {:error, Error.invalid_argument(":sections must be a list, got #{inspect(other)}")}
  end

  defp put_optional(body, _key, nil), do: body
  defp put_optional(body, key, value), do: Map.put(body, key, value)
end

defmodule KYCCentral.Docs do
  @moduledoc "Ask questions about the product in natural language."

  alias KYCCentral.{Error, Transport}

  @max_history 12

  @doc """
  Ask the documentation assistant a question.

  ## Options

    * `:history` — prior turns for follow-up questions, at most #{@max_history},
      each `%{role: "user" | "assistant", content: "..."}`.
    * `:receive_timeout` — timeout in milliseconds for this call. Defaults to 120
      seconds, or the client's `:receive_timeout` if that is longer. Must be a
      positive integer.
  """
  @spec ask(KYCCentral.t(), String.t(), keyword()) :: {:ok, map()} | {:error, Error.t()}
  def ask(client, message, opts \\ []) do
    history = opts[:history] || []
    timeout = Transport.ai_receive_timeout(client, opts)

    cond do
      not is_binary(message) or String.trim(message) == "" ->
        {:error, Error.invalid_argument("message must be a non-empty string")}

      length(history) > @max_history ->
        {:error,
         Error.invalid_argument(
           ":history accepts at most #{@max_history} turns, got #{length(history)}"
         )}

      match?({:error, _}, timeout) ->
        timeout

      true ->
        {:ok, timeout} = timeout
        body = %{"message" => message}
        body = if history == [], do: body, else: Map.put(body, "history", history)
        Transport.request(client, :post, "/docs/ask", body: body, receive_timeout: timeout)
    end
  end
end
