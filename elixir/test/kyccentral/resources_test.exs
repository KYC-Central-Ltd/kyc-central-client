defmodule KYCCentral.ResourcesTest do
  @moduledoc "Every resource function targets the URL and body the API documents."

  use ExUnit.Case, async: true

  alias KYCCentral.{Error, Stub}

  # Stored as module/function/extra-argument tuples rather than anonymous
  # functions: the list is escaped into generated tests at compile time, and
  # closures cannot be escaped.
  @routes [
    {KYCCentral.Companies, :get, ["00445790"], "/v1/companies/00445790"},
    {KYCCentral.Companies, :dossier, ["00445790"], "/v1/companies/00445790/dossier"},
    {KYCCentral.Companies, :officers, ["00445790"], "/v1/companies/00445790/officers"},
    {KYCCentral.Companies, :pscs, ["00445790"],
     "/v1/companies/00445790/persons-with-significant-control"},
    {KYCCentral.Companies, :psc_statements, ["00445790"],
     "/v1/companies/00445790/persons-with-significant-control-statements"},
    {KYCCentral.Companies, :psc_chain_depth, ["00445790"],
     "/v1/companies/00445790/psc-chain-depth"},
    {KYCCentral.Companies, :psc_chain_tree, ["00445790"],
     "/v1/companies/00445790/psc-chain-tree"},
    {KYCCentral.Companies, :charges, ["00445790"], "/v1/companies/00445790/charges"},
    {KYCCentral.Companies, :charge, ["00445790", "chg1"], "/v1/companies/00445790/charges/chg1"},
    {KYCCentral.Companies, :insolvency, ["00445790"], "/v1/companies/00445790/insolvency"},
    {KYCCentral.Companies, :disqualifications, ["00445790"],
     "/v1/companies/00445790/disqualifications"},
    {KYCCentral.Companies, :officer_disqualification, ["00445790", "off1"],
     "/v1/companies/00445790/officers/off1/disqualification"},
    {KYCCentral.Companies, :officer_appointments, ["off1"],
     "/v1/companies/officers/off1/appointments"},
    {KYCCentral.Companies, :filing_history, ["00445790"],
     "/v1/companies/00445790/filing-history"},
    {KYCCentral.Companies, :filing_extract, ["00445790", "tx1"],
     "/v1/companies/00445790/filing-history/tx1/extract"},
    {KYCCentral.Companies, :statement_of_capital, ["00445790"],
     "/v1/companies/00445790/statement-of-capital"},
    {KYCCentral.Companies, :search, ["tesco"], "/v1/companies/search"},
    {KYCCentral.Companies, :search_officers, ["smith"], "/v1/companies/search/officers"},
    {KYCCentral.Companies, :advanced_search, [], "/v1/companies/advanced-search"},
    {KYCCentral.RuleSets, :list, [], "/v1/rule-sets"},
    {KYCCentral.Rules, :list, [], "/v1/rules"},
    {KYCCentral.Rules, :fields, [], "/v1/rules/fields"},
    {KYCCentral.Jobs, :get, ["job-1"], "/v1/jobs/job-1"},
    {KYCCentral.Jurisdictions, :list, [], "/v1/jurisdictions"},
    {KYCCentral.Jurisdictions, :check, ["Iran"], "/v1/jurisdictions/check"},
    {KYCCentral.OffshoreJurisdictions, :list, [], "/v1/offshore-jurisdictions"},
    {KYCCentral.OffshoreJurisdictions, :check, ["Panama"], "/v1/offshore-jurisdictions/check"},
    {KYCCentral.Sanctions, :status, [], "/v1/sanctions/status"},
    {KYCCentral.Sanctions, :meta, [], "/v1/sanctions/meta"},
    {KYCCentral.Sanctions, :screen, ["Alice"], "/v1/sanctions/screen"},
    {KYCCentral.Sanctions, :entities, [], "/v1/sanctions/entities"},
    {KYCCentral.News, :status, [], "/v1/news/status"},
    {KYCCentral.News, :screen_company, ["00445790"], "/v1/news/screen-company"},
    {KYCCentral.OffshoreLeaks, :status, [], "/v1/offshore-leaks/status"},
    {KYCCentral.OffshoreLeaks, :node, ["n1"], "/v1/offshore-leaks/node/n1"},
    {KYCCentral.OffshoreLeaks, :screen_company, ["00445790"],
     "/v1/offshore-leaks/screen-company"},
    {KYCCentral.FCA, :status, [], "/v1/fca/status"},
    {KYCCentral.FCA, :search, ["acme"], "/v1/fca/search"},
    {KYCCentral.FCA, :firm, ["123456"], "/v1/fca/firm/123456"},
    {KYCCentral.FCA, :firm_names, ["123456"], "/v1/fca/firm/123456/names"},
    {KYCCentral.FCA, :firm_individuals, ["123456"], "/v1/fca/firm/123456/individuals"},
    {KYCCentral.FCA, :screen_individuals, ["00445790"], "/v1/fca/screen-individuals"},
    {KYCCentral.FCA, :check_individual, ["Alice"], "/v1/fca/check-individual"},
    {KYCCentral.GLEIF, :company, ["00445790"], "/v1/gleif/company"},
    {KYCCentral.IndividualInsolvency, :screen_company, ["00445790"],
     "/v1/individual-insolvency/screen-company"},
    {KYCCentral.Charity, :status, [], "/v1/charity/status"},
    {KYCCentral.Charity, :search, ["oxfam"], "/v1/charity/search"},
    {KYCCentral.Charity, :get, ["1234"], "/v1/charity/charity/1234"},
    {KYCCentral.Charity, :trustees, ["1234"], "/v1/charity/charity/1234/trustees"},
    {KYCCentral.HMRCVat, :status, [], "/v1/hmrc-vat/status"},
    {KYCCentral.HMRCVat, :check, ["GB123456789"], "/v1/hmrc-vat/check"},
    {KYCCentral.Analysis, :status, [], "/v1/analysis/status"},
    {KYCCentral, :data_source_health, [], "/health/data-sources"}
  ]

  for {module, function, args, path} <- @routes do
    test "#{inspect(module)}.#{function} hits #{path}" do
      {client, agent} = Stub.client([Stub.json(%{})])

      assert {:ok, _} = apply(unquote(module), unquote(function), [client | unquote(args)])
      assert Stub.path(agent) == unquote(path)
    end
  end

  describe "batch screening bodies" do
    test "posts a names body" do
      {client, agent} = Stub.client([Stub.json(%{})])

      assert {:ok, _} =
               KYCCentral.Sanctions.screen_names(client, ["Alice Example", "  Bob Example  ", ""])

      # Blank entries dropped, surrounding whitespace trimmed.
      assert Stub.body(agent) == %{"names" => ["Alice Example", "Bob Example"]}
      assert Stub.path(agent) == "/v1/sanctions/screen-names"
    end

    test "rejects an empty batch before making a request" do
      {client, agent} = Stub.client([Stub.json(%{})])

      assert {:error, %Error{kind: :invalid_argument}} =
               KYCCentral.Sanctions.screen_names(client, [])

      assert {:error, %Error{kind: :invalid_argument}} =
               KYCCentral.OffshoreLeaks.screen_names(client, ["", "   "])

      assert Stub.call_count(agent) == 0
    end

    test "enforces the documented batch cap" do
      {client, _agent} = Stub.client([Stub.json(%{})])
      names = Enum.map(1..501, &"name #{&1}")

      assert {:error, %Error{kind: :invalid_argument, message: message}} =
               KYCCentral.Sanctions.screen_names(client, names)

      assert message =~ "at most 500"
    end

    test "adverse media has no client-side cap, since the API's is tunable" do
      {client, agent} = Stub.client([Stub.json(%{})])
      names = Enum.map(1..501, &"name #{&1}")

      assert {:ok, _} = KYCCentral.News.search_names(client, names)
      assert length(Stub.body(agent)["names"]) == 501
    end
  end

  describe "entity search" do
    test "accepts atom- and string-keyed entities" do
      {client, agent} = Stub.client([Stub.json(%{})])

      assert {:ok, _} =
               KYCCentral.News.search_entities(client, [
                 %{key: "psc-1", names: ["Alice Example", "A. Example"]},
                 %{"key" => "psc-2", "names" => ["Bob Example"]}
               ])

      assert Stub.body(agent) == %{
               "entities" => [
                 %{"key" => "psc-1", "names" => ["Alice Example", "A. Example"]},
                 %{"key" => "psc-2", "names" => ["Bob Example"]}
               ]
             }
    end

    test "validates the entity shape" do
      {client, _agent} = Stub.client([Stub.json(%{})])

      assert {:error, %Error{kind: :invalid_argument, message: key_message}} =
               KYCCentral.News.search_entities(client, [%{names: ["Alice"]}])

      assert key_message =~ ":key"

      assert {:error, %Error{kind: :invalid_argument, message: names_message}} =
               KYCCentral.News.search_entities(client, [%{key: "psc-1", names: []}])

      assert names_message =~ "at least one name"

      assert {:error, %Error{kind: :invalid_argument}} =
               KYCCentral.News.search_entities(client, [])
    end
  end

  describe "analysis and docs" do
    test "builds the analysis body" do
      {client, agent} = Stub.client([Stub.json(%{})])

      assert {:ok, _} =
               KYCCentral.Analysis.company(client, "00445790",
                 rule_set_id: "quick",
                 sections: ["ownership"]
               )

      assert Stub.body(agent) == %{
               "company_number" => "00445790",
               "rule_set_id" => "quick",
               "sections" => ["ownership"]
             }
    end

    test "validates the filing extract mode" do
      {client, _agent} = Stub.client([Stub.json(%{})])

      assert {:error, %Error{kind: :invalid_argument, message: message}} =
               KYCCentral.Analysis.filing_extract(client, "00445790", "tx1", mode: "summarise")

      assert message =~ "must be one of"
    end

    test "defaults the filing extract mode to extract" do
      {client, agent} = Stub.client([Stub.json(%{})])

      assert {:ok, _} = KYCCentral.Analysis.filing_extract(client, "00445790", "tx1")
      assert Stub.body(agent)["mode"] == "extract"
    end

    test "validates documentation questions" do
      {client, _agent} = Stub.client([Stub.json(%{})])

      assert {:error, %Error{kind: :invalid_argument}} = KYCCentral.Docs.ask(client, "   ")

      history = List.duplicate(%{role: "user", content: "x"}, 13)

      assert {:error, %Error{kind: :invalid_argument, message: message}} =
               KYCCentral.Docs.ask(client, "hi", history: history)

      assert message =~ "at most 12"
    end

    test "AI endpoints default to a 120 second timeout" do
      {client, agent} = Stub.client([Stub.json(%{})])

      assert {:ok, _} = KYCCentral.Analysis.company(client, "00445790")
      assert {:ok, _} = KYCCentral.Analysis.adverse_media_overview(client, "00445790")
      assert {:ok, _} = KYCCentral.Analysis.filing_extract(client, "00445790", "tx1")
      assert {:ok, _} = KYCCentral.Docs.ask(client, "hi")

      for index <- 0..3, do: assert(Stub.call(agent, index).receive_timeout == 120_000)
    end

    test "other endpoints keep the client timeout" do
      {client, agent} = Stub.client([Stub.json(%{})])

      assert {:ok, _} = KYCCentral.RuleSets.list(client)
      assert Stub.call(agent).receive_timeout == 30_000
    end

    test "a per-call :receive_timeout overrides the default" do
      {client, agent} = Stub.client([Stub.json(%{})])

      assert {:ok, _} = KYCCentral.Analysis.company(client, "00445790", receive_timeout: 5_000)
      assert {:ok, _} = KYCCentral.Docs.ask(client, "hi", receive_timeout: 5_000)
      assert Stub.call(agent, 0).receive_timeout == 5_000
      assert Stub.call(agent, 1).receive_timeout == 5_000
    end

    test "a client with a longer timeout keeps it for AI endpoints" do
      {client, agent} = Stub.client([Stub.json(%{})], receive_timeout: 300_000)

      assert {:ok, _} = KYCCentral.Analysis.company(client, "00445790")
      assert Stub.call(agent).receive_timeout == 300_000
    end

    test "rejects an invalid per-call :receive_timeout before any request" do
      {client, agent} = Stub.client([Stub.json(%{})])

      for bad <- [0, -1, 1.5, "10"] do
        assert {:error, %Error{kind: :invalid_argument}} =
                 KYCCentral.Analysis.company(client, "00445790", receive_timeout: bad)

        assert {:error, %Error{kind: :invalid_argument}} =
                 KYCCentral.Analysis.adverse_media_overview(client, "00445790",
                   receive_timeout: bad
                 )

        assert {:error, %Error{kind: :invalid_argument}} =
                 KYCCentral.Analysis.filing_extract(client, "00445790", "tx1",
                   receive_timeout: bad
                 )

        assert {:error, %Error{kind: :invalid_argument}} =
                 KYCCentral.Docs.ask(client, "hi", receive_timeout: bad)
      end

      assert Stub.call_count(agent) == 0
    end
  end

  test "advanced search repeats list filters" do
    {client, agent} = Stub.client([Stub.json(%{})])

    assert {:ok, _} =
             KYCCentral.Companies.advanced_search(client,
               company_name_includes: "tesco",
               company_status: ["active", "liquidation"]
             )

    assert Stub.query_values(agent, "company_status") == ["active", "liquidation"]
    assert Stub.query_value(agent, "company_name_includes") == "tesco"
  end
end
