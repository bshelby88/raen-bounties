import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  raenPlugin,
  RaenMcpClient,
  lawLookupAction,
  disputeLetterAction,
  imageGenerateAction,
  contractAnalyzeAction,
  toolFinderAction,
} from "../dist/index.mjs";

describe("RAEN ElizaOS Plugin Structure", () => {
  it("exports valid ElizaOS Plugin object with metadata", () => {
    assert.equal(raenPlugin.name, "raen");
    assert.ok(raenPlugin.description.includes("RAEN"));
    assert.equal(Array.isArray(raenPlugin.actions), true);
    assert.equal(raenPlugin.actions.length, 5);
  });

  it("exposes all 5 required BOUNTY-01 actions", () => {
    const actionNames = raenPlugin.actions.map((a) => a.name);
    assert.ok(actionNames.includes("LAW_LOOKUP"), "Missing LAW_LOOKUP");
    assert.ok(actionNames.includes("DISPUTE_LETTER"), "Missing DISPUTE_LETTER");
    assert.ok(actionNames.includes("IMAGE_GENERATE"), "Missing IMAGE_GENERATE");
    assert.ok(actionNames.includes("CONTRACT_ANALYZE"), "Missing CONTRACT_ANALYZE");
    assert.ok(actionNames.includes("TOOL_FINDER"), "Missing TOOL_FINDER");
  });

  it("conforms to ElizaOS Action interface for all actions", () => {
    for (const action of raenPlugin.actions) {
      assert.equal(typeof action.name, "string");
      assert.ok(Array.isArray(action.similes), `${action.name} missing similes`);
      assert.equal(typeof action.description, "string");
      assert.equal(typeof action.validate, "function");
      assert.equal(typeof action.handler, "function");
      assert.ok(Array.isArray(action.examples), `${action.name} missing examples`);
      assert.ok(action.examples.length > 0, `${action.name} has no examples`);
    }
  });
});

describe("Action Validation & Trigger Matching", () => {
  const dummyRuntime = { getSetting: () => undefined };

  it("lawLookupAction validates legal and regulatory triggers", async () => {
    assert.equal(
      await lawLookupAction.validate(dummyRuntime, { content: { text: "What is FCRA permissible purpose?" } }),
      true
    );
    assert.equal(
      await lawLookupAction.validate(dummyRuntime, { content: { text: "Tell me about debt collection laws" } }),
      true
    );
    assert.equal(
      await lawLookupAction.validate(dummyRuntime, { content: { text: "What is the weather in Paris?" } }),
      false
    );
  });

  it("disputeLetterAction validates dispute requests", async () => {
    assert.equal(
      await disputeLetterAction.validate(dummyRuntime, { content: { text: "Draft a credit dispute letter" } }),
      true
    );
    assert.equal(
      await disputeLetterAction.validate(dummyRuntime, { content: { text: "How to dispute inaccurate reporting?" } }),
      true
    );
    assert.equal(
      await disputeLetterAction.validate(dummyRuntime, { content: { text: "Write me a love poem" } }),
      false
    );
  });

  it("imageGenerateAction validates generation requests", async () => {
    assert.equal(
      await imageGenerateAction.validate(dummyRuntime, { content: { text: "Generate an image of a cyber court" } }),
      true
    );
    assert.equal(
      await imageGenerateAction.validate(dummyRuntime, { content: { text: "Explain quantum mechanics" } }),
      false
    );
  });

  it("contractAnalyzeAction validates contract review requests", async () => {
    assert.equal(
      await contractAnalyzeAction.validate(dummyRuntime, { content: { text: "Analyze this contract indemnity clause" } }),
      true
    );
    assert.equal(
      await contractAnalyzeAction.validate(dummyRuntime, { content: { text: "Review terms of service" } }),
      true
    );
    assert.equal(
      await contractAnalyzeAction.validate(dummyRuntime, { content: { text: "Order a pizza" } }),
      false
    );
  });

  it("toolFinderAction validates tool discovery requests", async () => {
    assert.equal(
      await toolFinderAction.validate(dummyRuntime, { content: { text: "List available RAEN tools" } }),
      true
    );
    assert.equal(
      await toolFinderAction.validate(dummyRuntime, { content: { text: "Find MCP tools for legal" } }),
      true
    );
    assert.equal(
      await toolFinderAction.validate(dummyRuntime, { content: { text: "What is 2 + 2?" } }),
      false
    );
  });
});

describe("RaenMcpClient & JSON-RPC Protocol", () => {
  it("initializes with default gateway and config", () => {
    const client = new RaenMcpClient({ apiKey: "test-dev-key" });
    assert.equal(client.getApiKey(), "test-dev-key");
    assert.equal(client.getGatewayUrl(), "https://raen-mcp-gateway.fly.dev/mcp");
  });

  it("correctly handles 402 payment challenge responses", async () => {
    // Intercept with mock server/fetch returning 402
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
      assert.ok(res.challenge.accepts.length > 0);
      assert.equal(res.challenge.accepts[0].amount, "50000");
    } finally {
      global.fetch = originalFetch;
    }
  });

  it("handles successful JSON-RPC tool responses", async () => {
    const originalFetch = global.fetch;
    try {
      global.fetch = async (_url, init) => {
        const body = JSON.parse(init.body);
        assert.equal(body.jsonrpc, "2.0");
        assert.equal(body.method, "tools/call");
        assert.equal(body.params.name, "raen_law_lookup");
        assert.equal(body.params.arguments.topic, "statute of limitations");

        return new Response(
          JSON.stringify({
            jsonrpc: "2.0",
            id: body.id,
            result: {
              content: [
                {
                  type: "text",
                  text: "FCRA § 605: Most adverse items report for 7 years.",
                },
              ],
            },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      };

      const client = new RaenMcpClient();
      const res = await client.callTool("raen_law_lookup", { topic: "statute of limitations" });
      assert.equal(res.ok, true);
      assert.ok(res.data.content[0].text.includes("FCRA § 605"));
    } finally {
      global.fetch = originalFetch;
    }
  });
});
