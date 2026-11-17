import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { RaenCatalogService } from "../dist/extension.js";

describe("RAEN Catalog Service & llms.txt Parser", () => {
  const sampleLlmsTxt = `
# RAEN — Royal Agentic Enterprises
> Twelve production x402 micropayment services on Base Mainnet.

## Benchmark & Proof
- [Autonomous Operations Benchmark v1](https://bshelby88.github.io/raen-agent-directory/benchmark.html): 19/19 endpoint quality gate, $0.10 tx revenue.

## Paid Services (x402, pay per call, $0.01–$5.00)
- [royal-ruby-x402](https://royal-ruby-x402.fly.dev): flagship document engine, $0.05/call.
- [dispute-forge-x402](https://dispute-forge-x402.fly.dev): consumer dispute letter generation, $0.10 USDC.
- [dispute-forge-worker](https://dispute-forge-worker.raen.workers.dev): dispute-forge on Cloudflare Workers, $0.75/call.
- [contract-eye-x402](https://contract-eye-x402.fly.dev): contract risk analysis.
`;

  it("parses llms.txt correctly into structured SKU entities", () => {
    const service = new RaenCatalogService();
    const skus = service.parseLlmsTxt(sampleLlmsTxt);

    assert.equal(skus.length, 5);

    const royalRuby = skus.find((s) => s.id === "royal-ruby-x402");
    assert.ok(royalRuby, "royal-ruby-x402 not found");
    assert.equal(royalRuby.price, "$0.05");
    assert.equal(royalRuby.category, "fleet-services");
    assert.equal(royalRuby.manifestUrl, "https://royal-ruby-x402.fly.dev/.well-known/x402.json");

    const disputeWorker = skus.find((s) => s.id === "dispute-forge-worker");
    assert.ok(disputeWorker, "dispute-forge-worker not found");
    assert.equal(disputeWorker.price, "$0.75");
    assert.equal(disputeWorker.category, "workers");

    const benchmark = skus.find((s) => s.id.includes("benchmark"));
    assert.ok(benchmark, "benchmark not found");
    assert.equal(benchmark.category, "reference");
  });

  it("combines MCP tools with catalog items", async () => {
    const mockMcpClient = {
      getGatewayUrl: () => "https://raen-mcp-gateway.fly.dev/mcp",
      listTools: async () => [
        {
          name: "raen_law_lookup",
          description: "US consumer-protection law citations. $0.05 USDC.",
          annotations: { title: "RAEN Law Lookup" },
        },
      ],
    };

    const service = new RaenCatalogService(undefined, mockMcpClient);
    const originalFetch = global.fetch;
    try {
      global.fetch = async () => new Response(sampleLlmsTxt, { status: 200 });
      const skus = await service.fetchCatalog(true);

      const mcpTool = skus.find((s) => s.id === "raen_law_lookup");
      assert.ok(mcpTool, "MCP tool not included");
      assert.equal(mcpTool.category, "mcp-tools");
      assert.equal(mcpTool.price, "$0.05 USDC");
      assert.ok(skus.length >= 6);
    } finally {
      global.fetch = originalFetch;
    }
  });
});
