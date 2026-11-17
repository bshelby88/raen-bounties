import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { RaenMcpClient, generateCursorMcpConfig, generateOneLiner } from "../dist/extension.js";

describe("RaenMcpClient Protocol Handling", () => {
  it("formats JSON-RPC 2.0 messages correctly", async () => {
    let capturedBody = null;
    let capturedHeaders = null;

    const originalFetch = global.fetch;
    try {
      global.fetch = async (url, init) => {
        capturedBody = JSON.parse(init.body);
        capturedHeaders = init.headers;
        return new Response(
          JSON.stringify({
            jsonrpc: "2.0",
            id: capturedBody.id,
            result: { protocolVersion: "2025-03-26" },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      };

      const client = new RaenMcpClient(undefined, "secret-test-dev-key");
      const res = await client.initialize();

      assert.equal(capturedBody.jsonrpc, "2.0");
      assert.equal(capturedBody.method, "initialize");
      assert.equal(capturedHeaders["Authorization"], "Bearer secret-test-dev-key");
      assert.equal(res.protocolVersion, "2025-03-26");
    } finally {
      global.fetch = originalFetch;
    }
  });

  it("handles 402 challenge gracefully with structured receipt", async () => {
    const originalFetch = global.fetch;
    try {
      global.fetch = async () => {
        return new Response(
          JSON.stringify({
            x402Version: 2,
            error: "Payment required",
            accepts: [
              {
                scheme: "exact",
                network: "eip155:8453",
                amount: "50000",
                payTo: "0x9b8a27e03CEbA490953cDa8AB1291c0E13bAf72f",
              },
            ],
          }),
          { status: 402, headers: { "Content-Type": "application/json" } }
        );
      };

      const client = new RaenMcpClient();
      const res = await client.callTool("raen_law_lookup", { topic: "FCRA" });

      assert.equal(res.ok, false);
      assert.equal(res.paymentRequired, true);
      assert.equal(res.challenge.accepts[0].amount, "50000");
      assert.equal(res.challenge.accepts[0].payTo, "0x9b8a27e03CEbA490953cDa8AB1291c0E13bAf72f");
    } finally {
      global.fetch = originalFetch;
    }
  });

  it("captures payment response receipt headers on success", async () => {
    const originalFetch = global.fetch;
    try {
      global.fetch = async () => {
        const headers = new Headers({
          "Content-Type": "application/json",
          "payment-response": "base64-settlement-receipt-data",
        });
        return new Response(
          JSON.stringify({
            jsonrpc: "2.0",
            id: 1,
            result: { content: [{ type: "text", text: "Legal research text" }] },
          }),
          { status: 200, headers }
        );
      };

      const client = new RaenMcpClient(undefined, "dev-key-123");
      const res = await client.callTool("raen_law_lookup", { topic: "FCRA" });

      assert.equal(res.ok, true);
      assert.equal(res.receipt, "base64-settlement-receipt-data");
      assert.equal(res.data.content[0].text, "Legal research text");
    } finally {
      global.fetch = originalFetch;
    }
  });
});

describe("Cursor MCP Configuration Generator", () => {
  it("generates valid .cursor/mcp.json structure with auth headers", () => {
    const config = generateCursorMcpConfig("my-key-abc", "https://raen-mcp-gateway.fly.dev/mcp");
    assert.ok(config.mcpServers.raen);
    assert.equal(config.mcpServers.raen.url, "https://raen-mcp-gateway.fly.dev/mcp");
    assert.equal(config.mcpServers.raen.headers.Authorization, "Bearer my-key-abc");
  });

  it("generates one-liner JSON string", () => {
    const str = generateOneLiner("test-key");
    const parsed = JSON.parse(str);
    assert.ok(parsed.mcpServers.raen);
  });
});
