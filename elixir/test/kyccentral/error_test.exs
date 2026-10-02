defmodule KYCCentral.ErrorTest do
  @moduledoc "Status codes map onto the documented error kinds."

  use ExUnit.Case, async: true

  alias KYCCentral.{Error, Stub}

  @kinds [
    {400, :bad_request},
    {401, :authentication},
    {403, :permission_denied},
    {404, :not_found},
    {422, :unprocessable_entity},
    {429, :rate_limit},
    {500, :server_error},
    {502, :server_error},
    {503, :service_unavailable},
    {418, :unexpected_status}
  ]

  for {status, kind} <- @kinds do
    test "#{status} maps to #{kind}" do
      {client, _agent} = Stub.client([Stub.json(%{"detail" => "nope"}, unquote(status))])

      assert {:error, error} = KYCCentral.RuleSets.list(client)
      assert error.kind == unquote(kind)
      assert error.status == unquote(status)
      assert error.detail == "nope"
      assert error.message =~ "nope"
    end
  end

  test "errors are exceptions, so they can be raised" do
    {client, _agent} = Stub.client([Stub.json(%{"detail" => "nope"}, 404)])
    {:error, error} = KYCCentral.RuleSets.list(client)

    assert Exception.message(error) =~ "nope"
    assert_raise Error, fn -> raise error end
  end

  test "rate limit errors expose Retry-After" do
    response =
      {429, Jason.encode!(%{"detail" => "Rate limit exceeded"}),
       %{"content-type" => ["application/json"], "Retry-After" => ["30"]}}

    {client, _agent} = Stub.client([response])

    assert {:error, %Error{kind: :rate_limit, retry_after: 30.0}} =
             KYCCentral.RuleSets.list(client)
  end

  test "503 errors expose Retry-After, and have none without the header" do
    with_header =
      {503, Jason.encode!(%{"detail" => "down"}),
       %{"content-type" => ["application/json"], "Retry-After" => ["300"]}}

    {client, _agent} = Stub.client([with_header])

    assert {:error, %Error{kind: :service_unavailable, retry_after: 300.0}} =
             KYCCentral.RuleSets.list(client)

    {client, _agent} = Stub.client([Stub.json(%{"detail" => "down"}, 503)])

    assert {:error, %Error{kind: :service_unavailable, retry_after: nil}} =
             KYCCentral.RuleSets.list(client)
  end

  test "header lookup is case-insensitive, as HTTP header names are" do
    headers = %{"Retry-After" => ["30"], "content-type" => ["application/json"]}

    assert Error.header(headers, "retry-after") == "30"
    assert Error.header(headers, "Retry-After") == "30"
    assert Error.header(headers, "missing") == nil
  end

  test "header lookup accepts a plain list of tuples" do
    assert Error.header([{"retry-after", "12"}], "Retry-After") == "12"
  end

  test "validation errors are flattened into the message" do
    body = %{
      "detail" => [
        %{"loc" => ["body", "names"], "msg" => "field required", "type" => "missing"},
        %{"loc" => ["query", "q"], "msg" => "too long", "type" => "value_error"}
      ]
    }

    {client, _agent} = Stub.client([Stub.json(body, 422)])

    assert {:error, %Error{kind: :unprocessable_entity} = error} =
             KYCCentral.RuleSets.list(client)

    assert error.detail =~ "names: field required"
    assert error.detail =~ "query.q: too long"
    # The structured body stays reachable for callers that want the raw errors.
    assert is_list(error.body["detail"])
  end

  test "a non-JSON error body does not crash decoding" do
    {client, _agent} =
      Stub.client([{502, "<html>Bad Gateway</html>", %{"content-type" => ["text/html"]}}])

    assert {:error, %Error{kind: :server_error, status: 502, body: "<html>Bad Gateway</html>"}} =
             KYCCentral.RuleSets.list(client)
  end

  test "an empty success body decodes to nil" do
    {client, _agent} = Stub.client([{204, "", %{}}])

    assert {:ok, nil} = KYCCentral.RuleSets.list(client)
  end

  test "malformed JSON falls back to the raw body rather than raising" do
    {client, _agent} =
      Stub.client([{200, "{not json", %{"content-type" => ["application/json"]}}])

    assert {:ok, "{not json"} = KYCCentral.RuleSets.list(client)
  end
end
