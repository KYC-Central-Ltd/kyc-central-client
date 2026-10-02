defmodule KYCCentral.ClientTest do
  @moduledoc "Client construction, headers, URL building and retry behaviour."

  use ExUnit.Case, async: true

  alias KYCCentral.{Error, Stub}

  describe "new/1" do
    test "defaults to the production base URL and anonymous access" do
      client = KYCCentral.new(api_key: nil)

      assert client.base_url == "https://api.kyccentral.co.uk"
      refute KYCCentral.authenticated?(client)
    end

    test "reads credentials from the environment" do
      System.put_env("KYCCENTRAL_API_KEY", "env-key")
      System.put_env("KYCCENTRAL_BASE_URL", "https://dev-api.test.invalid/")
      on_exit(fn -> System.delete_env("KYCCENTRAL_API_KEY") end)
      on_exit(fn -> System.delete_env("KYCCENTRAL_BASE_URL") end)

      client = KYCCentral.new()

      assert KYCCentral.authenticated?(client)
      # Trailing slash is normalised away so path joins never double up.
      assert client.base_url == "https://dev-api.test.invalid"
    end

    test "prefers explicit options over the environment" do
      System.put_env("KYCCENTRAL_API_KEY", "env-key")
      on_exit(fn -> System.delete_env("KYCCENTRAL_API_KEY") end)

      client = KYCCentral.new(api_key: "explicit", base_url: Stub.base_url())

      assert client.api_key == "explicit"
      assert client.base_url == Stub.base_url()
    end

    test "treats a blank key as anonymous" do
      refute KYCCentral.authenticated?(KYCCentral.new(api_key: ""))
    end

    test "rejects nonsense settings" do
      assert_raise ArgumentError, fn -> KYCCentral.new(receive_timeout: 0) end
      assert_raise ArgumentError, fn -> KYCCentral.new(max_retries: -1) end
    end
  end

  describe "requests" do
    test "sends the API key, accept and user-agent headers" do
      {client, agent} = Stub.client([Stub.json([])])

      assert {:ok, []} = KYCCentral.RuleSets.list(client)

      assert Stub.header(agent, "x-api-key") == "test-key"
      assert Stub.header(agent, "accept") == "application/json"
      assert Stub.header(agent, "user-agent") =~ "kyccentral-elixir/"
    end

    test "omits the API key header when anonymous" do
      {client, agent} = Stub.client([Stub.json(%{})], api_key: nil)

      assert {:ok, _} = KYCCentral.Jurisdictions.list(client)
      assert Stub.header(agent, "x-api-key") == nil
    end

    test "sets content-type only when there is a body" do
      {client, agent} = Stub.client([Stub.json(%{}), Stub.json(%{})])

      assert {:ok, _} = KYCCentral.Sanctions.status(client)
      assert Stub.header(agent, "content-type") == nil

      assert {:ok, _} = KYCCentral.Sanctions.screen_names(client, ["Alice Example"])
      assert Stub.header(agent, "content-type", 1) == "application/json"
    end

    test "sends custom default headers" do
      {client, agent} = Stub.client([Stub.json([])], headers: [{"x-trace", "abc"}])

      assert {:ok, _} = KYCCentral.RuleSets.list(client)
      assert Stub.header(agent, "x-trace") == "abc"
    end

    test "versions business endpoints but not health" do
      {client, agent} = Stub.client([Stub.json(%{"status" => "ok"}), Stub.json([])])

      assert {:ok, %{"status" => "ok"}} = KYCCentral.health(client)
      assert Stub.path(agent) == "/health"

      assert {:ok, _} = KYCCentral.RuleSets.list(client)
      assert Stub.path(agent, 1) == "/v1/rule-sets"
    end

    test "drops unset query parameters" do
      {client, agent} = Stub.client([Stub.json(%{"items" => []})])

      assert {:ok, _} = KYCCentral.Companies.search(client, "tesco")

      assert Stub.query_value(agent, "q") == "tesco"
      # Neither optional parameter was supplied, so neither should appear.
      assert Stub.query_value(agent, "items_per_page") == nil
      assert Stub.query_value(agent, "start_index") == nil
    end

    test "repeats list parameters once per value" do
      {client, agent} = Stub.client([Stub.json(Stub.assessment_payload())])

      assert {:ok, _} =
               KYCCentral.KYC.assess(client, "00445790",
                 confirmed_media_urls: ["https://a.example", "https://b.example"]
               )

      assert Stub.query_values(agent, "confirmed_media_url") == [
               "https://a.example",
               "https://b.example"
             ]
    end

    test "percent-encodes path segments" do
      {client, agent} = Stub.client([Stub.json(%{})])

      # Officer ids are opaque upstream tokens and can contain URL-significant bytes.
      assert {:ok, _} = KYCCentral.Companies.officer_appointments(client, "abc/def+gh")
      assert Stub.call(agent).url =~ "abc%2Fdef%2Bgh"
    end

    test "rejects blank path segments before making a request" do
      {client, agent} = Stub.client([Stub.json(%{})])

      assert {:error, %Error{kind: :invalid_argument, message: message}} =
               KYCCentral.Companies.get(client, "   ")

      assert message =~ "company_number"
      assert Stub.call_count(agent) == 0
    end
  end

  describe "retries" do
    test "retries a retryable status and then succeeds" do
      {client, agent} =
        Stub.client(
          [Stub.json(%{"detail" => "warming up"}, 503), Stub.json([%{"id" => "default"}])],
          max_retries: 2
        )

      assert {:ok, [%{"id" => "default"}]} = KYCCentral.RuleSets.list(client)
      assert Stub.call_count(agent) == 2
    end

    test "does not retry client errors" do
      {client, agent} =
        Stub.client([Stub.json(%{"detail" => "Company not found"}, 404)], max_retries: 3)

      assert {:error, %Error{kind: :not_found}} = KYCCentral.Companies.get(client, "99999999")
      # A 404 will not become true on a second attempt.
      assert Stub.call_count(agent) == 1
    end

    test "gives up on a retryable status once retries are exhausted" do
      {client, agent} = Stub.client([Stub.json(%{"detail" => "down"}, 503)], max_retries: 1)

      assert {:error, %Error{kind: :service_unavailable}} = KYCCentral.RuleSets.list(client)
      assert Stub.call_count(agent) == 2
    end

    test "surfaces connection failures after retrying" do
      {client, agent} =
        Stub.failing_client({:failed_connect, [{:to_address, {~c"host", 443}}]}, max_retries: 1)

      assert {:error, %Error{kind: :connection}} = KYCCentral.RuleSets.list(client)
      assert Stub.call_count(agent) == 2
    end

    test "reports timeouts distinctly from other connection failures" do
      {client, _agent} = Stub.failing_client(:timeout, max_retries: 0)

      assert {:error, %Error{kind: :timeout, message: message}} = KYCCentral.RuleSets.list(client)
      assert message =~ "timed out"
    end

    test "recognises a nested httpc connect timeout" do
      reason = {:failed_connect, [{:to_address, {~c"host", 443}}, {:inet, [:inet], :timeout}]}
      {client, _agent} = Stub.failing_client(reason, max_retries: 0)

      assert {:error, %Error{kind: :timeout}} = KYCCentral.RuleSets.list(client)
    end

    test "a POST that times out is not retried" do
      {client, agent} =
        Stub.sequence_client([{:error, :timeout}, Stub.json(%{"ok" => true})], max_retries: 2)

      assert {:error, %Error{kind: :timeout}} = KYCCentral.Docs.ask(client, "hi")
      assert Stub.call_count(agent) == 1
    end

    test "a POST is retried when the connection was refused" do
      refused =
        {:failed_connect, [{:to_address, {~c"host", 443}}, {:inet, [:inet], :econnrefused}]}

      {client, agent} =
        Stub.sequence_client([{:error, refused}, Stub.json(%{"ok" => true})], max_retries: 2)

      assert {:ok, %{"ok" => true}} = KYCCentral.Docs.ask(client, "hi")
      assert Stub.call_count(agent) == 2
    end

    test "a POST is not retried after a connect timeout" do
      reason = {:failed_connect, [{:to_address, {~c"host", 443}}, {:inet, [:inet], :timeout}]}

      {client, agent} =
        Stub.sequence_client([{:error, reason}, Stub.json(%{"ok" => true})], max_retries: 2)

      assert {:error, %Error{kind: :timeout}} = KYCCentral.Docs.ask(client, "hi")
      assert Stub.call_count(agent) == 1
    end

    test "a POST is not retried after an unsafe transport error" do
      {client, agent} =
        Stub.sequence_client([{:error, :closed}, Stub.json(%{"ok" => true})], max_retries: 2)

      assert {:error, %Error{kind: :connection}} = KYCCentral.Docs.ask(client, "hi")
      assert Stub.call_count(agent) == 1
    end

    test "a POST is not retried on a 502" do
      {client, agent} =
        Stub.sequence_client(
          [Stub.json(%{"detail" => "bad gateway"}, 502), Stub.json(%{"ok" => true})],
          max_retries: 2
        )

      assert {:error, %Error{status: 502}} = KYCCentral.Docs.ask(client, "hi")
      assert Stub.call_count(agent) == 1
    end

    test "a POST is retried on a 503 with Retry-After" do
      busy = {503, Jason.encode!(%{"detail" => "busy"}), %{"retry-after" => ["0"]}}

      {client, agent} =
        Stub.sequence_client([busy, Stub.json(%{"ok" => true})], max_retries: 2)

      assert {:ok, %{"ok" => true}} = KYCCentral.Docs.ask(client, "hi")
      assert Stub.call_count(agent) == 2
    end

    test "a POST is not retried on a 503 without Retry-After" do
      {client, agent} =
        Stub.sequence_client(
          [Stub.json(%{"detail" => "busy"}, 503), Stub.json(%{"ok" => true})],
          max_retries: 2
        )

      assert {:error, %Error{kind: :service_unavailable}} = KYCCentral.Docs.ask(client, "hi")
      assert Stub.call_count(agent) == 1
    end

    test "a GET that times out is retried" do
      {client, agent} =
        Stub.sequence_client([{:error, :timeout}, Stub.json([%{"id" => "default"}])],
          max_retries: 2
        )

      assert {:ok, [%{"id" => "default"}]} = KYCCentral.RuleSets.list(client)
      assert Stub.call_count(agent) == 2
    end

    test "a GET with Retry-After exceeding max backoff (8s) is not retried" do
      rate_limited = {429, Jason.encode!(%{"detail" => "too fast"}), %{"retry-after" => ["60"]}}

      {client, agent} =
        Stub.sequence_client([rate_limited, Stub.json([%{"id" => "default"}])],
          max_retries: 2
        )

      assert {:error, %Error{kind: :rate_limit, retry_after: 60.0}} =
               KYCCentral.RuleSets.list(client)

      assert Stub.call_count(agent) == 1
    end

    test "a GET with Retry-After of 0 is retried" do
      rate_limited = {429, Jason.encode!(%{"detail" => "too fast"}), %{"retry-after" => ["0"]}}

      {client, agent} =
        Stub.sequence_client([rate_limited, Stub.json([%{"id" => "default"}])],
          max_retries: 2
        )

      assert {:ok, [%{"id" => "default"}]} = KYCCentral.RuleSets.list(client)
      assert Stub.call_count(agent) == 2
    end

    test "a GET with 503 and Retry-After exceeding max backoff is not retried" do
      busy = {503, Jason.encode!(%{"detail" => "busy"}), %{"retry-after" => ["60"]}}

      {client, agent} =
        Stub.sequence_client([busy, Stub.json([%{"id" => "default"}])], max_retries: 2)

      assert {:error, %Error{status: 503}} = KYCCentral.RuleSets.list(client)
      assert Stub.call_count(agent) == 1
    end
  end
end
