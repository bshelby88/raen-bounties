/**
 * RaenMcpClient: High-performance streamable HTTP client for the RAEN MCP Gateway
 */
import type { McpCallResult, McpToolSchema, RaenPluginConfig } from "./types.js";

export const DEFAULT_GATEWAY_URL = "https://raen-mcp-gateway.fly.dev/mcp";
export const DEFAULT_TIMEOUT_MS = 25000;

export class RaenMcpClient {
  private gatewayUrl: string;
  private apiKey?: string;
  private timeoutMs: number;
  private requestId: number = 1;

  constructor(config: RaenPluginConfig = {}) {
    this.gatewayUrl = (config.gatewayUrl || process.env.RAEN_GATEWAY_URL || DEFAULT_GATEWAY_URL).replace(/\/+$/, "");
    this.apiKey = config.apiKey || process.env.RAEN_API_KEY || process.env.RAEN_MCP_KEY;
    this.timeoutMs = config.timeoutMs || DEFAULT_TIMEOUT_MS;
  }

  public getApiKey(): string | undefined {
    return this.apiKey;
  }

  public setApiKey(key: string): void {
    this.apiKey = key;
  }

  public getGatewayUrl(): string {
    return this.gatewayUrl;
  }

  /**
   * Send a JSON-RPC 2.0 message to the MCP gateway.
   */
  private async postJsonRpc<T>(method: string, params: any = {}): Promise<T> {
    const id = this.requestId++;
    const body = JSON.stringify({
      jsonrpc: "2.0",
      id,
      method,
      params,
    });

    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      "User-Agent": "@elizaos/plugin-raen/1.0.0",
      "Accept": "application/json",
    };

    if (this.apiKey) {
      headers["Authorization"] = `Bearer ${this.apiKey.trim()}`;
    }

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.timeoutMs);

    try {
      const resp = await fetch(this.gatewayUrl, {
        method: "POST",
        headers,
        body,
        signal: controller.signal,
      });

      clearTimeout(timeout);

      // Handle HTTP 402 Payment Required specifically
      if (resp.status === 402) {
        const errorData = await resp.json().catch(() => ({}));
        const err = new Error(
          `x402 Payment Required: ${(errorData as any)?.error || "Payment required to execute paid MCP tool"}`
        );
        (err as any).status = 402;
        (err as any).challenge = errorData;
        throw err;
      }

      if (resp.status === 401 || resp.status === 403) {
        throw new Error(`Authentication failed (${resp.status}): Invalid or missing RAEN Bearer dev key.`);
      }

      if (!resp.ok) {
        const text = await resp.text().catch(() => "");
        throw new Error(`Gateway returned HTTP ${resp.status}: ${text}`);
      }

      const json = await resp.json() as any;
      if (json.error) {
        throw new Error(`MCP Error [${json.error.code}]: ${json.error.message}`);
      }

      return json.result as T;
    } catch (err: any) {
      clearTimeout(timeout);
      if (err.name === "AbortError") {
        throw new Error(`Gateway request timed out after ${this.timeoutMs}ms`);
      }
      throw err;
    }
  }

  /**
   * Initializes the MCP connection.
   */
  public async initialize(): Promise<any> {
    return this.postJsonRpc("initialize", {
      protocolVersion: "2025-03-26",
      capabilities: {},
      clientInfo: {
        name: "@elizaos/plugin-raen",
        version: "1.0.0",
      },
    });
  }

  /**
   * Lists available tools from the RAEN MCP gateway.
   */
  public async listTools(): Promise<McpToolSchema[]> {
    const res = await this.postJsonRpc<{ tools: McpToolSchema[] }>("tools/list", {});
    return res?.tools || [];
  }

  /**
   * Invokes an MCP tool by name.
   */
  public async callTool(name: string, args: Record<string, any>): Promise<McpCallResult> {
    try {
      const res = await this.postJsonRpc<any>("tools/call", {
        name,
        arguments: args,
      });
      return {
        ok: true,
        data: res,
      };
    } catch (err: any) {
      if (err.status === 402) {
        return {
          ok: false,
          paymentRequired: true,
          challenge: err.challenge,
          error: err.message,
        };
      }
      return {
        ok: false,
        error: err.message || String(err),
      };
    }
  }
}
