defmodule KYCCentral.BlankKeyTest do
  @moduledoc "An empty or whitespace-only API key means no key. Touches the environment, so not async."

  use ExUnit.Case, async: false

  alias KYCCentral.Stub

  setup do
    previous = System.get_env("KYCCENTRAL_API_KEY")

    on_exit(fn ->
      if previous,
        do: System.put_env("KYCCENTRAL_API_KEY", previous),
        else: System.delete_env("KYCCENTRAL_API_KEY")
    end)

    System.delete_env("KYCCENTRAL_API_KEY")
    :ok
  end

  defp assert_anonymous(client, agent) do
    refute KYCCentral.authenticated?(client)
    assert client.api_key == nil
    assert {:ok, _} = KYCCentral.Jurisdictions.list(client)
    assert Stub.header(agent, "x-api-key") == nil
  end

  test "an explicit empty key is no key" do
    {client, agent} = Stub.client([Stub.json(%{})], api_key: "")
    assert_anonymous(client, agent)
  end

  test "an explicit whitespace-only key is no key" do
    {client, agent} = Stub.client([Stub.json(%{})], api_key: "  \t ")
    assert_anonymous(client, agent)
  end

  test "an empty KYCCENTRAL_API_KEY is no key" do
    System.put_env("KYCCENTRAL_API_KEY", "")
    {client, agent} = Stub.client([Stub.json(%{})], api_key: System.get_env("KYCCENTRAL_API_KEY"))
    assert_anonymous(client, agent)

    # And through the real environment lookup in `new/1`.
    refute KYCCentral.authenticated?(KYCCentral.new([]))
  end

  test "a whitespace-only KYCCENTRAL_API_KEY is no key" do
    System.put_env("KYCCENTRAL_API_KEY", "   ")
    refute KYCCentral.authenticated?(KYCCentral.new([]))
  end
end
