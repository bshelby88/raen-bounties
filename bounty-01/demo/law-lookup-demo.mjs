#!/usr/bin/env node
/**
 * Live demonstration of @elizaos/plugin-raen against https://raen-mcp-gateway.fly.dev/mcp
 */
import { RaenMcpClient, lawLookupAction, toolFinderAction } from "../dist/index.mjs";

console.log("==================================================================");
console.log("  ELIZAOS RAEN PLUGIN — LIVE MCP GATEWAY DEMO");
console.log("==================================================================\n");

async function main() {
  const apiKey = process.env.RAEN_API_KEY || process.env.RAEN_MCP_KEY;
  const client = new RaenMcpClient({ apiKey });

  console.log(`[1] Connecting to MCP Gateway at: ${client.getGatewayUrl()}`);
  if (apiKey) {
    console.log(`[+] Authenticated with Bearer key: ${apiKey.slice(0, 8)}...`);
  } else {
    console.log(`[!] Running in unauthenticated mode (set RAEN_API_KEY to execute paid tool calls)`);
  }

  // Step 1: Initialize MCP session against live gateway
  console.log("\n[2] Initializing MCP protocol handshake (JSON-RPC initialize)...");
  try {
    const initRes = await client.initialize();
    console.log("    Handshake Success!");
    console.log(`    Server Name   : ${initRes.serverInfo?.name}`);
    console.log(`    Server Version: ${initRes.serverInfo?.version}`);
    console.log(`    Protocol Ver  : ${initRes.protocolVersion}`);
    console.log(`    Instructions  : ${initRes.serverInfo?.instructions?.slice(0, 85)}...`);
  } catch (err) {
    console.error(`    Handshake Failed: ${err.message}`);
    process.exit(1);
  }

  // Step 2: Discover available tools from live gateway
  console.log("\n[3] Discovering active tools from live gateway (JSON-RPC tools/list)...");
  const tools = await client.listTools();
  console.log(`    Discovered ${tools.length} active RAEN MCP tools:`);
  for (const t of tools) {
    console.log(`    - ${t.name.padEnd(25)} : ${t.description.slice(0, 70)}...`);
  }

  // Step 3: Run TOOL_FINDER action via ElizaOS action handler
  console.log("\n[4] Executing ElizaOS TOOL_FINDER Action...");
  const dummyRuntime = {
    getSetting: (k) => process.env[k],
  };

  await toolFinderAction.handler(
    dummyRuntime,
    { content: { text: "List legal research tools" } },
    {},
    { query: "law" },
    (resp) => {
      console.log("    [ElizaOS Callback Output]:");
      console.log(resp.text);
    }
  );

  // Step 4: Run LAW_LOOKUP action via ElizaOS action handler
  const testTopic = "debt collection calls at work under FDCPA";
  console.log(`\n[5] Executing ElizaOS LAW_LOOKUP Action for topic: "${testTopic}"...`);

  await lawLookupAction.handler(
    dummyRuntime,
    { content: { text: `Please look up the law on ${testTopic}` } },
    {},
    { topic: testTopic },
    (resp) => {
      console.log("    [ElizaOS Callback Action]:", resp.action);
      console.log("    [ElizaOS Callback Text]:");
      console.log(resp.text);
    }
  );

  console.log("\n==================================================================");
  console.log("  DEMO COMPLETE: All protocol communications verified live.");
  console.log("==================================================================");
}

main().catch((err) => {
  console.error("Fatal error:", err);
  process.exit(1);
});
