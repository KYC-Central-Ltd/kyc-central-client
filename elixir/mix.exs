defmodule KYCCentral.MixProject do
  use Mix.Project

  @version "0.10.0"
  @source_url "https://github.com/qualia91/kyccentral-elixir"

  def project do
    [
      app: :kyccentral,
      version: @version,
      elixir: "~> 1.15",
      start_permanent: Mix.env() == :prod,
      deps: deps(),
      elixirc_paths: elixirc_paths(Mix.env()),
      description:
        "Official Elixir client for the KYC Central API — UK company KYC and AML risk assessment.",
      package: package(),
      docs: docs(),
      name: "KYC Central",
      source_url: @source_url,
      dialyzer: [plt_add_apps: [:mix]],
      test_coverage: [tool: ExCoveralls, test_task: "test"]
    ]
  end

  # Lets `mix coveralls` run without MIX_ENV=test. Never list :excoveralls in
  # extra_applications: it is a test-only dependency, so a consumer's app would
  # fail to start looking for it.
  def cli do
    [preferred_envs: [coveralls: :test, "coveralls.json": :test, "coveralls.html": :test]]
  end

  def application do
    # :inets and :ssl back the default HTTP transport; both ship with OTP, which
    # is why this library needs no HTTP client dependency of its own.
    [extra_applications: [:logger, :inets, :ssl, :public_key]]
  end

  defp elixirc_paths(:test), do: ["lib", "test/support"]
  defp elixirc_paths(_), do: ["lib"]

  defp deps do
    [
      # Jason is the only runtime dependency: the default transport is OTP's own
      # :httpc, so adding this client to a project pulls in no HTTP stack. Swap
      # in Req, Finch or Tesla through the `:http` option if you prefer.
      {:jason, "~> 1.4"},
      {:ex_doc, "~> 0.34", only: :dev, runtime: false},
      {:dialyxir, "~> 1.4", only: :dev, runtime: false},
      {:excoveralls, "~> 0.18", only: :test, runtime: false},
      {:credo, "~> 1.7", only: [:dev, :test], runtime: false}
    ]
  end

  defp package do
    [
      licenses: ["MIT"],
      maintainers: ["KYC Central"],
      links: %{
        "GitHub" => @source_url,
        "Website" => "https://kyccentral.co.uk",
        "API reference" => "https://kyccentral.co.uk/api-docs",
        "Changelog" => "#{@source_url}/blob/main/CHANGELOG.md"
      },
      files: ~w(lib mix.exs README.md LICENSE CHANGELOG.md)
    ]
  end

  defp docs do
    [
      main: "readme",
      extras: ["README.md", "CHANGELOG.md", "CONTRIBUTING.md", "SECURITY.md"],
      source_ref: "v#{@version}",
      source_url: @source_url,
      groups_for_modules: [
        Core: [KYCCentral, KYCCentral.Assessment, KYCCentral.Error],
        "Companies and assessments": [
          KYCCentral.Companies,
          KYCCentral.KYC,
          KYCCentral.Jobs,
          KYCCentral.RuleSets,
          KYCCentral.Rules
        ],
        Screening: [
          KYCCentral.Sanctions,
          KYCCentral.News,
          KYCCentral.OffshoreLeaks,
          KYCCentral.FCA,
          KYCCentral.GLEIF,
          KYCCentral.IndividualInsolvency
        ],
        "Registries and reference data": [
          KYCCentral.Charity,
          KYCCentral.HMRCVat,
          KYCCentral.Jurisdictions,
          KYCCentral.OffshoreJurisdictions
        ],
        AI: [KYCCentral.Analysis, KYCCentral.Docs]
      ]
    ]
  end
end
