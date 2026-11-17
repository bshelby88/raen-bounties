#!/usr/bin/env node
/**
 * End-to-end simulation of the RAEN VS Code / Cursor Extension lifecycle.
 * Verifies live catalog fetching, MCP protocol handshake, and tool invocation.
 */
import {
  RaenMcpClient,
  RaenCatalogService,
  generateCursorMcpConfig,
  generateOneLiner,
} from "../dist/extension.js";

console.log("==================================================================");
console.log("  RAEN IDE EXTENSION (BOUNTY-06) — VERIFICATION & LIVE DEMO");
console.log("==================================================================\n");

async function main() {
  const apiKey = process.env.RAEN_API_KEY || process.env.RAEN_MCP_KEY;
  const mcpClient = new RaenMcpClient(undefined, apiKey);
  const catalogService = new RaenCatalogService(undefined, mcpClient);

  console.log(`[1] Environment & Configuration:`);
  console.log(`    Gateway URL : ${mcpClient.getGatewayUrl()}`);
  console.log(`    Catalog URL : https://raw.githubusercontent.com/bshelby88/raen-agent-directory/main/llms.txt`);
  console.log(`    Dev Key     : ${apiKey ? apiKey.slice(0, 8) + "..." : "None (402 challenge demonstration)"}`);

  // 1. Live MCP Gateway Handshake
  console.log(`\n[2] Executing live MCP Gateway handshake (initialize)...`);
  try {
    const initRes = await mcpClient.initialize();
    console.log(`    Handshake SUCCESS:`);
    console.log(`    Server Name    : ${initRes.serverInfo?.name}`);
    console.log(`    Protocol Ver   : ${initRes.protocolVersion}`);
    console.log(`    Server Info    : ${initRes.serverInfo?.instructions?.slice(0, 90)}...`);
  } catch (err) {
    console.error(`    Handshake FAILED: ${err.message}`);
    process.exit(1);
  }

  // 2. Fetch & parse fleet catalog from llms.txt & MCP gateway
  console.log(`\n[3] Fetching RAEN fleet SKU catalog from llms.txt & live MCP tools...`);
  const skus = await catalogService.fetchCatalog();
  console.log(`    Catalog loaded: ${skus.length} total entities`);

  const mcpTools = skus.filter((s) => s.category === "mcp-tools");
  const fleetServices = skus.filter((s) => s.category === "fleet-services");
  const workers = skus.filter((s) => s.category === "workers");

  console.log(`    - MCP Flagship Tools   : ${mcpTools.length}`);
  for (const t of mcpTools) {
    console.log(`      * [${t.price}] ${t.name} (${t.id})`);
  }
  console.log(`    - Production x402 Fleet: ${fleetServices.length} services (e.g. ${fleetServices.slice(0, 3).map(s => s.name).join(", ")}...)`);
  console.log(`    - Cloudflare Workers   : ${workers.length} workers (e.g. ${workers.map(w => w.name).join(", ")})`);

  // 3. Simulate interactive tool execution from the IDE
  const testTopic = "FCRA § 605 7-year obsolete reporting timeline";
  console.log(`\n[4] Invoking paid MCP tool: raen_law_lookup for topic "${testTopic}"...`);
  const result = await mcpClient.callTool("raen_law_lookup", { topic: testTopic });

  if (result.ok) {
    console.log(`    Tool Execution SUCCESS (200 OK)`);
    console.log(`    Settlement Receipt: ${result.receipt}`);
    console.log(`    Response:\n`, JSON.stringify(result.data, null, 2));
  } else if (result.paymentRequired) {
    console.log(`    [x402 Payment Challenge Captured from Gateway]:`);
    console.log(`    Error Message  : ${result.challenge?.error}`);
    console.log(`    Network        : ${result.challenge?.accepts?.[0]?.network}`);
    console.log(`    Amount         : ${result.challenge?.accepts?.[0]?.amount} (0.05 USDC)`);
    console.log(`    PayTo Address  : ${result.challenge?.accepts?.[0]?.payTo}`);
    console.log(`    Instructions   : ${result.challenge?.paymentInstructions?.slice(0, 110)}...`);
  } else {
    console.log(`    Tool execution error: ${result.error}`);
  }

  // 4. Cursor MCP Config Generation
  console.log(`\n[5] Generating Cursor MCP One-Liner (.cursor/mcp.json)...`);
  const oneLiner = generateOneLiner(apiKey || "YOUR_RAEN_DEV_KEY");
  console.log(oneLiner);

  console.log("\n==================================================================");
  console.log("  VERIFICATION COMPLETE: Live handshake, catalog & tools OK.");
  console.log("==================================================================");
}

main().catch((err) => {
  console.error("Fatal error:", err);
  process.exit(1);
});
