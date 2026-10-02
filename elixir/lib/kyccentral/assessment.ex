defmodule KYCCentral.RiskFlag do
  @moduledoc "A single risk signal raised against a company."

  @typedoc """
  A severity or risk level.

  `:unknown` is a value this client version does not recognise (for example a
  level added by a future API release). It ranks above `:critical`, so it is
  never filtered out by `KYCCentral.Assessment.flags_at_or_above/2`. The original
  string is on `:raw`.
  """
  @type severity :: :low | :medium | :high | :critical | :unknown

  @type t :: %__MODULE__{
          code: String.t(),
          severity: severity(),
          description: String.t(),
          raw: map()
        }

  defstruct [:code, :severity, :description, raw: %{}]
end

defmodule KYCCentral.RuleResult do
  @moduledoc "The per-rule breakdown of an assessment, including rules that passed."

  @type status :: :passed | :failed | :not_evaluated

  @type t :: %__MODULE__{
          code: String.t(),
          name: String.t(),
          description: String.t(),
          severity: KYCCentral.RiskFlag.severity(),
          status: status(),
          reason: String.t() | nil,
          raw: map()
        }

  defstruct [:code, :name, :description, :severity, :status, :reason, raw: %{}]
end

defmodule KYCCentral.Assessment do
  @moduledoc """
  The result of running a rule set against one company.

  Most endpoints in this API proxy or reshape upstream registry data and are
  returned as plain maps, so new upstream fields are never silently dropped. The
  assessment is the one response with a contract of its own, so it is modelled
  here — with the untouched payload kept on `:raw`.

  The `*_summary` fields hold the evidence each rule was evaluated against; each
  mirrors the corresponding standalone endpoint, so `:officers_summary` and
  `KYCCentral.Companies.officers/2` describe the same data.

  `:psc_chain_depth_capped` is true when the ownership walk hit its depth limit,
  so `:psc_chain_depth` is a lower bound (at least N layers).
  """

  alias KYCCentral.{RiskFlag, RuleResult}

  @severity_rank %{low: 0, medium: 1, high: 2, critical: 3, unknown: 4}

  # Explicit lookup tables rather than `String.to_existing_atom/1`: that would
  # depend on these atoms already being loaded, which typespecs alone do not
  # guarantee, and would raise on an unrecognised value from a future API release.
  @severities %{"low" => :low, "medium" => :medium, "high" => :high, "critical" => :critical}
  @statuses %{
    "passed" => :passed,
    "failed" => :failed,
    "not_evaluated" => :not_evaluated
  }

  @type t :: %__MODULE__{
          company_number: String.t(),
          company_name: String.t(),
          risk_level: RiskFlag.severity(),
          flags: [RiskFlag.t()],
          checked_at: String.t(),
          data_fetched_at: String.t(),
          psc_chain_depth: non_neg_integer(),
          psc_chain_depth_capped: boolean(),
          rule_results: [RuleResult.t()],
          timed_out_services: [String.t()],
          unavailable_services: [String.t()],
          failed_rules: [String.t()],
          pending_extractions: [String.t()],
          raw: map()
        }

  defstruct [
    :company_number,
    :company_name,
    :risk_level,
    :checked_at,
    :data_fetched_at,
    flags: [],
    psc_chain_depth: 0,
    psc_chain_depth_capped: false,

    # Companies House core data
    profile: %{},
    officers_summary: %{},
    psc_summary: %{},
    psc_statements_summary: %{},
    charges_summary: %{},
    insolvency_summary: %{},
    filing_summary: %{},
    disqualifications_summary: %{},
    corporate_disqualifications_summary: %{},
    officer_appointments_summary: %{},
    company_exemptions_summary: %{},
    confirmation_statements_summary: %{},
    cs01_document_summary: %{},
    statement_of_capital_summary: %{},

    # Screening and external data
    sanctions_summary: %{},
    adverse_media_summary: %{},
    fca_summary: %{},
    individual_insolvency_summary: %{},
    gleif_summary: %{},
    offshore_leaks_summary: %{},
    vat_summary: %{},

    # Run metadata
    timed_out_services: [],
    unavailable_services: [],
    failed_rules: [],
    rule_results: [],
    pending_extractions: [],
    raw: %{}
  ]

  @doc """
  Build an assessment from a decoded `/v1/kyc/assess` body.
  """
  @spec from_map(map()) :: t()
  def from_map(data) when is_map(data) do
    %__MODULE__{
      company_number: string(data["company_number"]),
      company_name: string(data["company_name"]),
      risk_level: severity(data["risk_level"]),
      flags: Enum.map(list(data["flags"]), &to_flag/1),
      checked_at: string(data["checked_at"]),
      data_fetched_at: string(data["data_fetched_at"]),
      psc_chain_depth: integer(data["psc_chain_depth"]),
      psc_chain_depth_capped: data["psc_chain_depth_capped"] == true,
      profile: object(data["profile"]),
      officers_summary: object(data["officers_summary"]),
      psc_summary: object(data["psc_summary"]),
      psc_statements_summary: object(data["psc_statements_summary"]),
      charges_summary: object(data["charges_summary"]),
      insolvency_summary: object(data["insolvency_summary"]),
      filing_summary: object(data["filing_summary"]),
      disqualifications_summary: object(data["disqualifications_summary"]),
      corporate_disqualifications_summary: object(data["corporate_disqualifications_summary"]),
      officer_appointments_summary: object(data["officer_appointments_summary"]),
      company_exemptions_summary: object(data["company_exemptions_summary"]),
      confirmation_statements_summary: object(data["confirmation_statements_summary"]),
      cs01_document_summary: object(data["cs01_document_summary"]),
      statement_of_capital_summary: object(data["statement_of_capital_summary"]),
      sanctions_summary: object(data["sanctions_summary"]),
      adverse_media_summary: object(data["adverse_media_summary"]),
      fca_summary: object(data["fca_summary"]),
      individual_insolvency_summary: object(data["individual_insolvency_summary"]),
      gleif_summary: object(data["gleif_summary"]),
      offshore_leaks_summary: object(data["offshore_leaks_summary"]),
      vat_summary: object(data["vat_summary"]),
      timed_out_services: strings(data["timed_out_services"]),
      unavailable_services: strings(data["unavailable_services"]),
      failed_rules: strings(data["failed_rules"]),
      rule_results: Enum.map(list(data["rule_results"]), &to_rule_result/1),
      pending_extractions: strings(data["pending_extractions"]),
      raw: data
    }
  end

  @doc "True when no rule in the set raised a flag."
  @spec clear?(t()) :: boolean()
  def clear?(%__MODULE__{flags: flags}), do: flags == []

  @doc """
  True when some data was unavailable, so the result is incomplete.

  That is when `:timed_out_services` or `:unavailable_services` is non-empty, or
  when any rule failed (`:failed_rules`) or extraction is pending
  (`:pending_extractions`).

  A partial assessment is still usable, but an absent flag is not proof of a
  clean result — treat it as "not yet screened" rather than "clear".
  """
  @spec partial?(t()) :: boolean()
  def partial?(%__MODULE__{} = assessment) do
    assessment.timed_out_services != [] or assessment.unavailable_services != [] or
      assessment.failed_rules != [] or assessment.pending_extractions != []
  end

  @doc "Flags matching any of `severities`."
  @spec flags_at(t(), [RiskFlag.severity()]) :: [RiskFlag.t()]
  def flags_at(%__MODULE__{flags: flags}, severities) when is_list(severities) do
    Enum.filter(flags, &(&1.severity in severities))
  end

  @doc """
  Flags at `severity` or more severe.

  A flag whose severity this client version does not recognise is `:unknown`,
  which ranks above `:critical`, so it is never filtered out. The original
  string is on the flag's `:raw`.
  """
  @spec flags_at_or_above(t(), RiskFlag.severity()) :: [RiskFlag.t()]
  def flags_at_or_above(%__MODULE__{flags: flags}, severity) do
    threshold = rank(severity)
    Enum.filter(flags, &(rank(&1.severity) >= threshold))
  end

  @doc "True when a flag with `code` was raised, e.g. `\"ACCOUNTS_OVERDUE\"`."
  @spec has_flag?(t(), String.t()) :: boolean()
  def has_flag?(%__MODULE__{flags: flags}, code), do: Enum.any?(flags, &(&1.code == code))

  @doc "The flag with `code`, or `nil` when it was not raised."
  @spec flag(t(), String.t()) :: RiskFlag.t() | nil
  def flag(%__MODULE__{flags: flags}, code), do: Enum.find(flags, &(&1.code == code))

  @doc "Rule results matching `status`."
  @spec rules_with_status(t(), RuleResult.status()) :: [RuleResult.t()]
  def rules_with_status(%__MODULE__{rule_results: results}, status) do
    Enum.filter(results, &(&1.status == status))
  end

  @doc "Numeric severity, ascending. Useful for sorting."
  @spec rank(RiskFlag.severity()) :: 0..4
  def rank(severity), do: Map.get(@severity_rank, severity, 0)

  defp to_flag(data) when is_map(data) do
    %RiskFlag{
      code: string(data["code"]),
      severity: severity(data["severity"]),
      description: string(data["description"]),
      raw: data
    }
  end

  defp to_rule_result(data) when is_map(data) do
    %RuleResult{
      code: string(data["code"]),
      name: string(data["name"]),
      description: string(data["description"]),
      severity: severity(data["severity"]),
      status: status(data["status"]),
      reason: data["reason"],
      raw: data
    }
  end

  # A future API release may add a severity or status this client predates, so
  # unknown values degrade rather than crashing the caller. An unrecognised
  # severity fails safe: it becomes `:unknown`, which ranks above `:critical`, so
  # it is never filtered out as low risk. The original string is still on `:raw`.
  defp severity(value) when is_binary(value) do
    Map.get(@severities, String.downcase(value), :unknown)
  end

  defp severity(_), do: :unknown

  defp status(value) when is_binary(value) do
    Map.get(@statuses, String.downcase(value), :not_evaluated)
  end

  defp status(_), do: :not_evaluated

  defp string(value) when is_binary(value), do: value
  defp string(nil), do: ""
  defp string(value), do: to_string(value)

  defp object(value) when is_map(value), do: value
  defp object(_), do: %{}

  defp list(value) when is_list(value), do: Enum.filter(value, &is_map/1)
  defp list(_), do: []

  defp strings(value) when is_list(value), do: Enum.map(value, &string/1)
  defp strings(_), do: []

  defp integer(value) when is_integer(value), do: value
  defp integer(_), do: 0
end
