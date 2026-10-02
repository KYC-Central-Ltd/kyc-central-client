defmodule KYCCentral.Sanctions do
  @moduledoc """
  Screen names against OFAC, the UN Security Council, the UK Sanctions List and
  the EU Financial Sanctions Files.

  Matching is approximate — these lists carry transliterated names, aliases and
  date-of-birth ranges — so treat every hit as a candidate for human review
  rather than a confirmed match.
  """

  import KYCCentral.Transport, only: [names_body: 2]

  alias KYCCentral.{Error, Transport}

  @typedoc "Maximum names per batch, as declared in the API schema."
  @type result :: {:ok, map()} | {:error, Error.t()}

  @max_names 500

  @doc "Maximum number of names accepted by `screen_names/3`."
  @spec max_names() :: pos_integer()
  def max_names, do: @max_names

  @doc "Whether the screening dataset is loaded and ready."
  @spec status(KYCCentral.t()) :: result()
  def status(client), do: Transport.request(client, :get, "/sanctions/status")

  @doc "Provenance of the loaded lists: sources, publication dates, record counts."
  @spec meta(KYCCentral.t()) :: result()
  def meta(client), do: Transport.request(client, :get, "/sanctions/meta")

  @doc """
  Screen a single name.

  ## Options

    * `:threshold` — fuzzy-match threshold, an integer from 1 to 100. Overrides
      the server default; lower values return more, weaker candidates.
    * `:vector_threshold` — vector-similarity threshold, from 0.0 to 1.0.
      Overrides the server default.
  """
  @spec screen(KYCCentral.t(), String.t(), keyword()) :: result()
  def screen(client, name, opts \\ []) do
    params = [name: name, threshold: opts[:threshold], vector_threshold: opts[:vector_threshold]]
    Transport.request(client, :get, "/sanctions/screen", params: params)
  end

  @doc """
  Screen up to #{@max_names} names in one request.

  Far cheaper than a loop over `screen/3`: one request against your rate limit
  instead of one per name.
  """
  @spec screen_names(KYCCentral.t(), [String.t()]) :: result()
  def screen_names(client, names) do
    with {:ok, body} <- names_body(names, @max_names) do
      Transport.request(client, :post, "/sanctions/screen-names", body: body)
    end
  end

  @doc """
  Browse the underlying sanctions entities.

  ## Options

    * `:search` — substring filter on entity name.
    * `:entity_type` — e.g. `"person"` or `"organization"`.
    * `:sanctioned` — filter to currently-designated entities.
    * `:dataset` — restrict to one source list, e.g. `"gb_fcdo_sanctions"`.
    * `:page`, `:page_size`
  """
  @spec entities(KYCCentral.t(), keyword()) :: result()
  def entities(client, opts \\ []) do
    params = [
      search: opts[:search],
      entity_type: opts[:entity_type],
      sanctioned: opts[:sanctioned],
      dataset: opts[:dataset],
      page: opts[:page],
      page_size: opts[:page_size]
    ]

    Transport.request(client, :get, "/sanctions/entities", params: params)
  end
end

defmodule KYCCentral.News do
  @moduledoc """
  Adverse media search. **Requires an active Professional subscription.**

  Name matching against news results is noisy by nature, so a hit here is a lead
  to review, not a finding. In an assessment these only raise a low-severity
  `ADVERSE_MEDIA_UNCONFIRMED` flag until an analyst confirms the article.
  """

  import KYCCentral.Transport, only: [names_body: 2, segment: 2]

  alias KYCCentral.{Error, Transport}

  @type result :: {:ok, map()} | {:error, Error.t()}

  @doc "Whether adverse media search is configured and available."
  @spec status(KYCCentral.t()) :: result()
  def status(client), do: Transport.request(client, :get, "/news/status")

  @doc """
  Search adverse media for a batch of names.

  The per-request cap is set server-side and can be tuned by the operator, so a
  large batch may be rejected with a 422 rather than client-side.
  """
  @spec search_names(KYCCentral.t(), [String.t()]) :: result()
  def search_names(client, names) do
    with {:ok, body} <- names_body(names, nil) do
      Transport.request(client, :post, "/news/search-names", body: body)
    end
  end

  @doc """
  Search adverse media for entities that each have several known names.

  Each entity is `%{key: "...", names: ["...", ...]}`. The key is yours to
  choose and is echoed back on the results, so use it to join hits onto your own
  records.
  """
  @spec search_entities(KYCCentral.t(), [map()]) :: result()
  def search_entities(client, entities) do
    with {:ok, body} <- entities_body(entities) do
      Transport.request(client, :post, "/news/search-entities", body: body)
    end
  end

  @doc "Search adverse media for a company and its officers and PSCs."
  @spec screen_company(KYCCentral.t(), String.t()) :: result()
  def screen_company(client, company_number) do
    with {:ok, number} <- segment(company_number, "company_number") do
      Transport.request(client, :get, "/news/screen-company", params: [company_number: number])
    end
  end

  defp entities_body([]) do
    {:error, Error.invalid_argument("entities must contain at least one entry")}
  end

  defp entities_body(entities) when is_list(entities) do
    Enum.reduce_while(entities, {:ok, []}, fn entity, {:ok, acc} ->
      key = entity |> fetch(:key) |> to_string() |> String.trim()

      names =
        entity
        |> fetch(:names)
        |> List.wrap()
        |> Enum.map(&(&1 |> to_string() |> String.trim()))
        |> Enum.reject(&(&1 == ""))

      cond do
        key == "" ->
          {:halt, {:error, Error.invalid_argument("each entity needs a non-empty :key")}}

        names == [] ->
          {:halt,
           {:error, Error.invalid_argument("entity #{inspect(key)} needs at least one name")}}

        true ->
          {:cont, {:ok, [%{"key" => key, "names" => names} | acc]}}
      end
    end)
    |> case do
      {:ok, built} -> {:ok, %{"entities" => Enum.reverse(built)}}
      {:error, _} = error -> error
    end
  end

  # Accepts atom- or string-keyed entity maps, since callers building them from
  # decoded JSON will have string keys.
  defp fetch(entity, key) when is_map(entity) do
    Map.get(entity, key) || Map.get(entity, to_string(key))
  end

  defp fetch(_entity, _key), do: nil
end

defmodule KYCCentral.OffshoreLeaks do
  @moduledoc """
  Screen against the ICIJ Offshore Leaks database.

  Covers the Panama, Paradise and Pandora Papers plus the Offshore Leaks and
  Bahamas Leaks datasets. As with adverse media, matches are name-based and
  unconfirmed hits only raise a low-severity flag in an assessment.
  """

  import KYCCentral.Transport, only: [names_body: 2, segment: 2]

  alias KYCCentral.{Error, Transport}

  @type result :: {:ok, map()} | {:error, Error.t()}

  @max_names 500

  @doc "Maximum number of names accepted by `screen_names/2`."
  @spec max_names() :: pos_integer()
  def max_names, do: @max_names

  @doc "Whether the Offshore Leaks dataset is available."
  @spec status(KYCCentral.t()) :: result()
  def status(client), do: Transport.request(client, :get, "/offshore-leaks/status")

  @doc "Screen up to #{@max_names} names against the leaks datasets."
  @spec screen_names(KYCCentral.t(), [String.t()]) :: result()
  def screen_names(client, names) do
    with {:ok, body} <- names_body(names, @max_names) do
      Transport.request(client, :post, "/offshore-leaks/screen-names", body: body)
    end
  end

  @doc "Screen a company and its officers and PSCs against the leaks datasets."
  @spec screen_company(KYCCentral.t(), String.t()) :: result()
  def screen_company(client, company_number) do
    with {:ok, number} <- segment(company_number, "company_number") do
      Transport.request(client, :get, "/offshore-leaks/screen-company",
        params: [company_number: number]
      )
    end
  end

  @doc """
  Fetch one leaks node — an entity, officer, intermediary or address.

  ## Options

    * `:name` — expected name, used to disambiguate when the id is ambiguous.
    * `:node_type` — expected node type, used the same way.
  """
  @spec node(KYCCentral.t(), String.t(), keyword()) :: result()
  def node(client, node_id, opts \\ []) do
    with {:ok, id} <- segment(node_id, "node_id") do
      params = [name: opts[:name], node_type: opts[:node_type]]
      Transport.request(client, :get, "/offshore-leaks/node/#{id}", params: params)
    end
  end
end

defmodule KYCCentral.GLEIF do
  @moduledoc "Global LEI Foundation lookups — legal entity identifiers and parent chains."

  import KYCCentral.Transport, only: [segment: 2]

  alias KYCCentral.{Error, Transport}

  @doc "The company's LEI record and its direct and ultimate parents."
  @spec company(KYCCentral.t(), String.t()) :: {:ok, map()} | {:error, Error.t()}
  def company(client, company_number) do
    with {:ok, number} <- segment(company_number, "company_number") do
      Transport.request(client, :get, "/gleif/company", params: [company_number: number])
    end
  end
end

defmodule KYCCentral.IndividualInsolvency do
  @moduledoc "Insolvency Service Individual Insolvency Register screening."

  import KYCCentral.Transport, only: [segment: 2]

  alias KYCCentral.{Error, Transport}

  @doc "Check a company's officers and PSCs for personal insolvency records."
  @spec screen_company(KYCCentral.t(), String.t()) :: {:ok, map()} | {:error, Error.t()}
  def screen_company(client, company_number) do
    with {:ok, number} <- segment(company_number, "company_number") do
      Transport.request(client, :get, "/individual-insolvency/screen-company",
        params: [company_number: number]
      )
    end
  end
end
