defmodule KYCCentral.Companies do
  @moduledoc """
  Companies House company, officer, PSC, charge and filing data.

  Available on every plan, except the four endpoints marked
  **Professional plan**.

  Company numbers are Companies House registration numbers — up to eight
  alphanumeric characters, e.g. `"00445790"` or `"SC123456"`. Leading zeroes are
  significant, so keep them as strings.
  """

  import KYCCentral.Transport, only: [segment: 2]

  alias KYCCentral.{Error, Transport}

  @type result :: {:ok, map()} | {:error, Error.t()}

  @doc """
  Search companies by name or number.

  ## Options

    * `:items_per_page` — page size. The API applies its own default and cap.
    * `:start_index` — zero-based offset for paging.
  """
  @spec search(KYCCentral.t(), String.t(), keyword()) :: result()
  def search(client, q, opts \\ []) do
    Transport.request(client, :get, "/companies/search", params: page_params(q, opts))
  end

  @doc "Search officers (directors, secretaries) by name across all companies."
  @spec search_officers(KYCCentral.t(), String.t(), keyword()) :: result()
  def search_officers(client, q, opts \\ []) do
    Transport.request(client, :get, "/companies/search/officers", params: page_params(q, opts))
  end

  @doc """
  Structured company search with status, type, SIC and date filters.

  ## Options

  All optional. Dates are `YYYY-MM-DD`. Each of `:company_status`,
  `:company_type` and `:sic_codes` takes a single value, matched exactly.

    * `:company_name_includes`, `:company_name_excludes`
    * `:company_status`, `:company_type`, `:sic_codes` — a single string each
    * `:location`
    * `:incorporated_from`, `:incorporated_to`
    * `:dissolved_from`, `:dissolved_to`
    * `:size`, `:start_index`, `:items_per_page`
  """
  @spec advanced_search(KYCCentral.t(), keyword()) :: result()
  def advanced_search(client, opts \\ []) do
    params = [
      company_name_includes: opts[:company_name_includes],
      company_name_excludes: opts[:company_name_excludes],
      company_status: opts[:company_status],
      company_type: opts[:company_type],
      location: opts[:location],
      sic_codes: opts[:sic_codes],
      incorporated_from: opts[:incorporated_from],
      incorporated_to: opts[:incorporated_to],
      dissolved_from: opts[:dissolved_from],
      dissolved_to: opts[:dissolved_to],
      size: opts[:size],
      start_index: opts[:start_index],
      items_per_page: opts[:items_per_page]
    ]

    Transport.request(client, :get, "/companies/advanced-search", params: params)
  end

  @doc "The company profile: name, status, type, dates, address, SIC codes."
  @spec get(KYCCentral.t(), String.t()) :: result()
  def get(client, company_number), do: company_path(client, company_number, "")

  @doc """
  Profile, officers, PSCs, charges, insolvency and filings in one call.

  Cheaper than issuing each lookup separately — one request against your rate
  limit instead of six.
  """
  @spec dossier(KYCCentral.t(), String.t()) :: result()
  def dossier(client, company_number), do: company_path(client, company_number, "/dossier")

  @doc "Appointed officers, including resigned ones."
  @spec officers(KYCCentral.t(), String.t()) :: result()
  def officers(client, company_number), do: company_path(client, company_number, "/officers")

  @doc """
  Suggest which registered company each unidentified corporate officer might be.

  Returns `%{"matches" => %{officer_name => [candidate, ...]}}`. Suggestions only,
  for a human to review; confirm one by passing `:confirmed_officer_company_links`
  to `KYCCentral.KYC.assess/3`.
  """
  @spec officer_company_matches(KYCCentral.t(), String.t()) :: result()
  def officer_company_matches(client, company_number) do
    company_path(client, company_number, "/officer-company-matches")
  end

  @doc "Registered beneficial owners (PSCs)."
  @spec pscs(KYCCentral.t(), String.t()) :: result()
  def pscs(client, company_number) do
    company_path(client, company_number, "/persons-with-significant-control")
  end

  @doc "PSC statements — the register's explanations for an absent PSC."
  @spec psc_statements(KYCCentral.t(), String.t()) :: result()
  def psc_statements(client, company_number) do
    company_path(client, company_number, "/persons-with-significant-control-statements")
  end

  @doc "How many corporate layers sit between the company and a real person."
  @spec psc_chain_depth(KYCCentral.t(), String.t()) :: result()
  def psc_chain_depth(client, company_number) do
    company_path(client, company_number, "/psc-chain-depth")
  end

  @doc "The full ownership chain as a tree, resolving corporate PSCs upwards."
  @spec psc_chain_tree(KYCCentral.t(), String.t()) :: result()
  def psc_chain_tree(client, company_number) do
    company_path(client, company_number, "/psc-chain-tree")
  end

  @doc "Registered charges (secured debt) against the company."
  @spec charges(KYCCentral.t(), String.t()) :: result()
  def charges(client, company_number), do: company_path(client, company_number, "/charges")

  @doc "One charge in full, including the persons entitled to it."
  @spec charge(KYCCentral.t(), String.t(), String.t()) :: result()
  def charge(client, company_number, charge_id) do
    with {:ok, number} <- segment(company_number, "company_number"),
         {:ok, id} <- segment(charge_id, "charge_id") do
      Transport.request(client, :get, "/companies/#{number}/charges/#{id}")
    end
  end

  @doc """
  Charge registration records already extracted for this company, as
  `%{"items" => [...]}`: the full charge-holder list and level-of-influence
  signals for each. Empty until `extract_charge_registration/3` has been run.
  """
  @spec charge_registrations(KYCCentral.t(), String.t()) :: result()
  def charge_registrations(client, company_number) do
    company_path(client, company_number, "/charges/registrations")
  end

  @doc "Insolvency cases. Returns an empty payload when there are none."
  @spec insolvency(KYCCentral.t(), String.t()) :: result()
  def insolvency(client, company_number), do: company_path(client, company_number, "/insolvency")

  @doc "Disqualified-director records across the company's officers."
  @spec disqualifications(KYCCentral.t(), String.t()) :: result()
  def disqualifications(client, company_number) do
    company_path(client, company_number, "/disqualifications")
  end

  @doc "Disqualification record for one officer of this company."
  @spec officer_disqualification(KYCCentral.t(), String.t(), String.t()) :: result()
  def officer_disqualification(client, company_number, officer_id) do
    with {:ok, number} <- segment(company_number, "company_number"),
         {:ok, officer} <- segment(officer_id, "officer_id") do
      Transport.request(
        client,
        :get,
        "/companies/#{number}/officers/#{officer}/disqualification"
      )
    end
  end

  @doc "Every appointment held by one officer, across all companies."
  @spec officer_appointments(KYCCentral.t(), String.t(), keyword()) :: result()
  def officer_appointments(client, officer_id, opts \\ []) do
    with {:ok, officer} <- segment(officer_id, "officer_id") do
      params = [items_per_page: opts[:items_per_page], start_index: opts[:start_index]]

      Transport.request(client, :get, "/companies/officers/#{officer}/appointments",
        params: params
      )
    end
  end

  @doc """
  Filing history. **Requires an active Professional subscription.**

  ## Options

    * `:category` — Companies House filing category, e.g. `"accounts"`,
      `"confirmation-statement"`, `"officers"`.
    * `:items_per_page`, `:start_index`
  """
  @spec filing_history(KYCCentral.t(), String.t(), keyword()) :: result()
  def filing_history(client, company_number, opts \\ []) do
    with {:ok, number} <- segment(company_number, "company_number") do
      params = [
        start_index: opts[:start_index],
        items_per_page: opts[:items_per_page],
        category: opts[:category]
      ]

      Transport.request(client, :get, "/companies/#{number}/filing-history", params: params)
    end
  end

  @doc """
  Structured data parsed out of one filing.

  **Requires an active Professional subscription.**
  """
  @spec filing_extract(KYCCentral.t(), String.t(), String.t()) :: result()
  def filing_extract(client, company_number, transaction_id) do
    with {:ok, number} <- segment(company_number, "company_number"),
         {:ok, transaction} <- segment(transaction_id, "transaction_id") do
      Transport.request(
        client,
        :get,
        "/companies/#{number}/filing-history/#{transaction}/extract"
      )
    end
  end

  @doc """
  Extract the full charge-holder list and level-of-influence signals for one
  charge, without spending AI credits.

  **Requires an active Professional subscription.**

  `charge_key` is the charge code (e.g. `"094462310004"`), or
  `"{company_number}-{charge_number}"` for pre-2013 charges. Paper and pre-2013
  forms have no text layer; the response is then
  `%{"needs_ai" => true, "charge_key" => ..., "filing_transaction_id" => ...}`
  and `KYCCentral.Analysis.charge_registration/4` can read the form instead.

  A blank `charge_key` returns an `:invalid_argument` error without making a
  request. The key is sent trimmed.
  """
  @spec extract_charge_registration(KYCCentral.t(), String.t(), String.t()) :: result()
  def extract_charge_registration(client, company_number, charge_key) do
    with {:ok, number} <- segment(company_number, "company_number"),
         {:ok, key} <- Transport.charge_key(charge_key) do
      Transport.request(client, :post, "/companies/#{number}/charges/registration",
        body: %{"charge_key" => key}
      )
    end
  end

  @doc """
  Share capital and shareholders from the latest confirmation statement.

  **Requires an active Professional subscription.**
  """
  @spec statement_of_capital(KYCCentral.t(), String.t()) :: result()
  def statement_of_capital(client, company_number) do
    company_path(client, company_number, "/statement-of-capital")
  end

  defp company_path(client, company_number, suffix) do
    with {:ok, number} <- segment(company_number, "company_number") do
      Transport.request(client, :get, "/companies/#{number}#{suffix}")
    end
  end

  defp page_params(q, opts) do
    [q: q, items_per_page: opts[:items_per_page], start_index: opts[:start_index]]
  end
end
