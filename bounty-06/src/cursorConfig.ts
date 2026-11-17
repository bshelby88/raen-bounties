import type { CursorMcpConfig } from "./types.js";

export function generateCursorMcpConfig(apiKey?: string, gatewayUrl?: string): CursorMcpConfig {
  const url = gatewayUrl || "https://raen-mcp-gateway.fly.dev/mcp";
  const config: CursorMcpConfig = {
    mcpServers: {
      raen: {
        url,
      },
    },
  };

  if (apiKey && apiKey.trim()) {
    config.mcpServers.raen!.headers = {
      Authorization: `Bearer ${apiKey.trim()}`,
    };
  }

  return config;
}

export function generateOneLiner(apiKey?: string, gatewayUrl?: string): string {
  const cfg = generateCursorMcpConfig(apiKey, gatewayUrl);
  return JSON.stringify(cfg, null, 2);
}
