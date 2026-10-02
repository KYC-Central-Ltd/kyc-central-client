defmodule KYCCentral.Charity do
  @moduledoc "Charity Commission for England and Wales lookups."

  import KYCCentral.Transport, only: [segment: 2]

  alias KYCCentral.{Error, Transport}

  @type result :: {:ok, map()} | {:error, Error.t()}

  @doc "Whether Charity Commission access is configured."
  @spec status(KYCCentral.t()) :: result()
  def status(client), do: Transport.request(client, :get, "/charity/status")

  @doc "Search registered charities by name."
  @spec search(KYCCentral.t(), String.t()) :: result()
  def search(client, q), do: Transport.request(client, :get, "/charity/search", params: [q: q])

  @doc """
  A charity's register entry.

  ## Options

    * `:suffix` — linked-charity suffix, an integer. Defaults to 0, the main
      charity.
  """
  @spec get(KYCCentral.t(), String.t(), keyword()) :: result()
  def get(client, registration_number, opts \\ []) do
    with {:ok, number} <- segment(registration_number, "registration_number") do
      Transport.request(client, :get, "/charity/charity/#{number}",
        params: [suffix: opts[:suffix]]
      )
    end
  end

  @doc "The charity's registered trustees."
  @spec trustees(KYCCentral.t(), String.t()) :: result()
  def trustees(client, registration_number) do
    with {:ok, number} <- segment(registration_number, "registration_number") do
      Transport.request(client, :get, "/charity/charity/#{number}/trustees")
    end
  end
end

defmodule KYCCentral.HMRCVat do
  @moduledoc "HMRC VAT registration lookups."

  alias KYCCentral.{Error, Transport}

  @type result :: {:ok, map()} | {:error, Error.t()}

  @doc "Whether HMRC VAT lookups are configured."
  @spec status(KYCCentral.t()) :: result()
  def status(client), do: Transport.request(client, :get, "/hmrc-vat/status")

  @doc "Check a UK VAT registration number, with or without the `GB` prefix."
  @spec check(KYCCentral.t(), String.t()) :: result()
  def check(client, vat_number) do
    Transport.request(client, :get, "/hmrc-vat/check", params: [vat_number: vat_number])
  end
end

defmodule KYCCentral.Jurisdictions do
  @moduledoc """
  FATF high-risk and increased-monitoring jurisdiction reference data.

  Updated after each FATF plenary — roughly February, June and October.
  """

  alias KYCCentral.{Error, Transport}

  @doc "The current FATF black list and grey list."
  @spec list(KYCCentral.t()) :: {:ok, term()} | {:error, Error.t()}
  def list(client), do: Transport.request(client, :get, "/jurisdictions")

  @doc "Whether one country is FATF-listed, and on which list."
  @spec check(KYCCentral.t(), String.t()) :: {:ok, map()} | {:error, Error.t()}
  def check(client, country) do
    Transport.request(client, :get, "/jurisdictions/check", params: [country: country])
  end
end

defmodule KYCCentral.OffshoreJurisdictions do
  @moduledoc "Offshore and shell-company jurisdiction reference data."

  alias KYCCentral.{Error, Transport}

  @doc "Known offshore jurisdictions and the keywords used to detect them."
  @spec list(KYCCentral.t()) :: {:ok, term()} | {:error, Error.t()}
  def list(client), do: Transport.request(client, :get, "/offshore-jurisdictions")

  @doc "Whether a name or address indicates an offshore jurisdiction."
  @spec check(KYCCentral.t(), String.t()) :: {:ok, map()} | {:error, Error.t()}
  def check(client, name) do
    Transport.request(client, :get, "/offshore-jurisdictions/check", params: [name: name])
  end
end
