defmodule KYCCentral.KYCTest do
  @moduledoc "Assessment parsing, argument validation and queued-job polling."

  use ExUnit.Case, async: true

  alias KYCCentral.{Assessment, Error, Stub}

  describe "assess/3" do
    test "parses the response into a typed assessment" do
      {client, _agent} = Stub.client([Stub.json(Stub.assessment_payload())])

      assert {:ok, %Assessment{} = assessment} = KYCCentral.KYC.assess(client, "00445790")

      assert assessment.company_name == "TESCO PLC"
      assert assessment.risk_level == :medium
      assert assessment.psc_chain_depth == 2
      refute assessment.psc_chain_depth_capped
      assert assessment.unavailable_services == []

      assert Enum.map(assessment.flags, & &1.code) == [
               "ACCOUNTS_OVERDUE",
               "ADVERSE_MEDIA_UNCONFIRMED"
             ]

      # Anything not mapped to a field is still reachable.
      assert assessment.raw["profile"]["company_status"] == "active"
    end

    test "exposes helpers over the flags" do
      {client, _agent} = Stub.client([Stub.json(Stub.assessment_payload())])
      {:ok, assessment} = KYCCentral.KYC.assess(client, "00445790")

      refute Assessment.clear?(assessment)
      refute Assessment.partial?(assessment)
      assert Assessment.flags_at(assessment, [:critical]) == []

      assert Enum.map(Assessment.flags_at_or_above(assessment, :high), & &1.code) ==
               ["ACCOUNTS_OVERDUE"]

      assert Assessment.has_flag?(assessment, "ACCOUNTS_OVERDUE")
      refute Assessment.has_flag?(assessment, "NOT_RAISED")
      assert Assessment.flag(assessment, "NOT_RAISED") == nil
      assert %{code: "ACCOUNTS_OVERDUE"} = Assessment.flag(assessment, "ACCOUNTS_OVERDUE")

      assert Enum.map(Assessment.rules_with_status(assessment, :passed), & &1.code) ==
               ["COMPANY_NOT_ACTIVE"]
    end

    test "marks assessments affected by an upstream timeout as partial" do
      payload = Map.put(Stub.assessment_payload(), "timed_out_services", ["sanctions"])
      {client, _agent} = Stub.client([Stub.json(payload)])

      assert {:ok, assessment} = KYCCentral.KYC.assess(client, "00445790")
      assert Assessment.partial?(assessment)
    end

    test "marks an assessment with only unavailable services as partial" do
      payload = Map.put(Stub.assessment_payload(), "unavailable_services", ["gleif"])
      {client, _agent} = Stub.client([Stub.json(payload)])

      assert {:ok, assessment} = KYCCentral.KYC.assess(client, "00445790")
      assert assessment.unavailable_services == ["gleif"]
      assert assessment.timed_out_services == []
      assert Assessment.partial?(assessment)
    end

    test "parses psc_chain_depth_capped, and defaults the new keys when absent" do
      payload = Map.put(Stub.assessment_payload(), "psc_chain_depth_capped", true)
      {client, _agent} = Stub.client([Stub.json(payload)])
      assert {:ok, %Assessment{psc_chain_depth_capped: true}} = KYCCentral.KYC.assess(client, "1")

      bare =
        Map.drop(Stub.assessment_payload(), ["psc_chain_depth_capped", "unavailable_services"])

      {client, _agent} = Stub.client([Stub.json(bare)])
      assert {:ok, assessment} = KYCCentral.KYC.assess(client, "1")
      assert assessment.psc_chain_depth_capped == false
      assert assessment.unavailable_services == []
    end

    test "sends the new confirmation and dismissal options" do
      {client, agent} = Stub.client([Stub.json(Stub.assessment_payload())])

      assert {:ok, _} =
               KYCCentral.KYC.assess(client, "00445790",
                 dismissed_media_urls: ["https://news.example/a", "https://news.example/b"],
                 dismissed_leak_ids: ["n1", "n2"],
                 confirmed_officer_company_links: ["ACME HOLDINGS||01234567"],
                 confirmed_fca_frn: "123456",
                 fca_not_applicable: true
               )

      assert Stub.query_values(agent, "dismissed_media_url") ==
               ["https://news.example/a", "https://news.example/b"]

      assert Stub.query_values(agent, "dismissed_leak_id") == ["n1", "n2"]

      assert Stub.query_values(agent, "confirmed_officer_company_link") ==
               ["ACME HOLDINGS||01234567"]

      assert Stub.query_values(agent, "confirmed_fca_frn") == ["123456"]
      assert Stub.query_values(agent, "fca_not_applicable") == ["true"]
    end

    test "fca_not_applicable is omitted when false or absent" do
      {client, agent} = Stub.client([Stub.json(Stub.assessment_payload())])

      assert {:ok, _} = KYCCentral.KYC.assess(client, "00445790", fca_not_applicable: false)
      assert {:ok, _} = KYCCentral.KYC.assess(client, "00445790")

      assert Stub.query_values(agent, "fca_not_applicable", 0) == []
      assert Stub.query_values(agent, "fca_not_applicable", 1) == []
      assert Stub.query_values(agent, "dismissed_leak_id", 1) == []
    end

    test "an unrecognised severity or risk level fails safe to :unknown" do
      payload = Stub.assessment_payload()
      flags = List.update_at(payload["flags"], 0, &Map.put(&1, "severity", "severe"))
      payload = payload |> Map.put("flags", flags) |> Map.put("risk_level", "severe")
      {client, _agent} = Stub.client([Stub.json(payload)])

      assert {:ok, assessment} = KYCCentral.KYC.assess(client, "00445790")
      assert assessment.risk_level == :unknown
      assert hd(assessment.flags).severity == :unknown
      assert hd(assessment.flags).raw["severity"] == "severe"
      assert assessment.raw["risk_level"] == "severe"

      assert "ACCOUNTS_OVERDUE" in Enum.map(
               Assessment.flags_at_or_above(assessment, :high),
               & &1.code
             )

      assert Enum.map(Assessment.flags_at_or_above(assessment, :critical), & &1.code) ==
               [hd(assessment.flags).code]

      assert Assessment.rank(:unknown) > Assessment.rank(:critical)
    end

    test "a missing or non-string severity is :unknown, a known one still maps" do
      payload = Stub.assessment_payload()

      flags =
        payload["flags"]
        |> List.update_at(0, &Map.delete(&1, "severity"))
        |> List.update_at(1, &Map.put(&1, "severity", "HIGH"))

      {client, _agent} = Stub.client([Stub.json(Map.put(payload, "flags", flags))])

      assert {:ok, assessment} = KYCCentral.KYC.assess(client, "00445790")
      assert Enum.map(assessment.flags, & &1.severity) == [:unknown, :high]
    end

    test "requires exactly one of a company number and :q" do
      {client, agent} = Stub.client([Stub.json(Stub.assessment_payload())])

      assert {:error, %Error{kind: :invalid_argument, message: message}} =
               KYCCentral.KYC.assess(client, [])

      assert message =~ "either"

      assert {:error, %Error{kind: :invalid_argument, message: both}} =
               KYCCentral.KYC.assess(client, "00445790", q: "tesco")

      assert both =~ "not both"
      assert Stub.call_count(agent) == 0
    end

    test "rejects an empty or whitespace-only company number before any request" do
      {client, agent} = Stub.client([Stub.json(Stub.assessment_payload())])

      for blank <- ["", "   "] do
        assert {:error, %Error{kind: :invalid_argument, message: message}} =
                 KYCCentral.KYC.assess(client, blank)

        assert message =~ "either"
      end

      assert Stub.call_count(agent) == 0
    end

    test "assesses the top search result when given a name" do
      {client, agent} = Stub.client([Stub.json(Stub.assessment_payload())])

      assert {:ok, _} = KYCCentral.KYC.assess(client, q: "tesco plc", rule_set_id: "quick")

      assert Stub.query_value(agent, "q") == "tesco plc"
      assert Stub.query_value(agent, "rule_set_id") == "quick"
      assert Stub.query_value(agent, "company_number") == nil
    end
  end

  describe "queued assessments" do
    defp queued, do: Stub.json(%{"job_id" => "job-123", "status" => "queued"}, 202)

    test "polls a queued job to completion" do
      {client, agent} =
        Stub.client([
          queued(),
          Stub.json(%{"job_id" => "job-123", "status" => "running"}),
          Stub.json(%{
            "job_id" => "job-123",
            "status" => "done",
            "result" => Stub.assessment_payload()
          })
        ])

      assert {:ok, %Assessment{company_name: "TESCO PLC"}} =
               KYCCentral.KYC.assess(client, "00445790", poll_interval: 1)

      assert Stub.call_count(agent) == 3
      assert Stub.path(agent, 1) == "/v1/jobs/job-123"
    end

    test "polls a job whose id is an integer" do
      {client, agent} =
        Stub.client([
          Stub.json(%{"job_id" => 123, "status" => "queued"}, 202),
          Stub.json(%{
            "job_id" => 123,
            "status" => "done",
            "result" => Stub.assessment_payload()
          })
        ])

      assert {:ok, %Assessment{company_name: "TESCO PLC"}} =
               KYCCentral.KYC.assess(client, "00445790", poll_interval: 1)

      assert Stub.path(agent, 1) == "/v1/jobs/123"
    end

    test "rejects non-positive polling parameters before any request" do
      {client, agent} = Stub.client([queued()])

      for {key, value} <- [
            poll_interval: 0,
            poll_interval: -5,
            poll_interval: 1.5,
            poll_timeout: 0,
            poll_timeout: -1,
            poll_timeout: "10"
          ] do
        assert {:error, %Error{kind: :invalid_argument, message: message}} =
                 KYCCentral.KYC.assess(client, "00445790", [{key, value}])

        assert message =~ inspect(key)
        assert message =~ "positive integer"
      end

      assert Stub.call_count(agent) == 0
    end

    test "returns the raw envelope when wait is false" do
      {client, _agent} = Stub.client([queued()])

      assert {:ok, %{"job_id" => "job-123", "status" => "queued"}} =
               KYCCentral.KYC.assess(client, "00445790", wait: false)
    end

    test "reports a failed job" do
      {client, _agent} =
        Stub.client([
          queued(),
          Stub.json(%{"job_id" => "job-123", "status" => "error", "error" => "upstream exploded"})
        ])

      assert {:error, %Error{kind: :job_failed, job_id: "job-123", message: message}} =
               KYCCentral.KYC.assess(client, "00445790", poll_interval: 1)

      assert message =~ "upstream exploded"
    end

    test "reports an expired result" do
      {client, _agent} =
        Stub.client([queued(), Stub.json(%{"job_id" => "job-123", "status" => "done"})])

      assert {:error, %Error{kind: :job_failed, message: message}} =
               KYCCentral.KYC.assess(client, "00445790", poll_interval: 1)

      assert message =~ "no longer available"
    end

    test "gives up after the poll timeout" do
      {client, _agent} =
        Stub.client([queued(), Stub.json(%{"job_id" => "job-123", "status" => "running"})])

      assert {:error, %Error{kind: :job_timeout, job_id: "job-123"}} =
               KYCCentral.KYC.assess(client, "00445790", poll_interval: 10, poll_timeout: 1)
    end
  end
end
