import type { McpCallResponse } from "./types.js";

export const DEFAULT_GATEWAY_URL = "https://raen-mcp-gateway.fly.dev/mcp";

export class RaenMcpClient {
  private gatewayUrl: string;
  private apiKey?: string;
  private timeoutMs: number;
  private reqId: number = 1;

  constructor(gatewayUrl: string = DEFAULT_GATEWAY_URL, apiKey?: string, timeoutMs: number = 25000) {
    this.gatewayUrl = gatewayUrl.replace(/\/+$/, "");
    this.apiKey = apiKey || process.env.RAEN_API_KEY || process.env.RAEN_MCP_KEY;
    this.timeoutMs = timeoutMs;
  }

  public setApiKey(key: string): void {
    this.apiKey = key;
  }

  public getApiKey(): string | undefined {
    return this.apiKey;
  }

  public getGatewayUrl(): string {
    return this.gatewayUrl;
  }

  public async postJsonRpc<T>(method: string, params: any = {}): Promise<{ result?: T; headers?: Headers; raw?: any }> {
    const id = this.reqId++;
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      "User-Agent": "raen-ide-extension/1.0.0",
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
        body: JSON.stringify({
          jsonrpc: "2.0",
          id,
          method,
          params,
        }),
        signal: controller.signal,
      });

      clearTimeout(timeout);

      if (resp.status === 402) {
        const errorJson = await resp.json().catch(() => ({}));
        const err: any = new Error(`x402 Payment Required: ${errorJson?.error || "Payment challenge"}`);
        err.status = 402;
        err.challenge = errorJson;
        throw err;
      }

      if (resp.status === 401 || resp.status === 403) {
        throw new Error(`Auth failed (${resp.status}): Invalid or missing Bearer key.`);
      }

      if (!resp.ok) {
        const txt = await resp.text().catch(() => "");
        throw new Error(`Gateway returned HTTP ${resp.status}: ${txt}`);
      }

      const json = (await resp.json()) as any;
      if (json.error) {
        throw new Error(`MCP Error [${json.error.code}]: ${json.error.message}`);
      }

      return {
        result: json.result as T,
        headers: resp.headers,
        raw: json,
      };
    } catch (err: any) {
      clearTimeout(timeout);
      if (err.name === "AbortError") {
        throw new Error(`Request timed out after ${this.timeoutMs}ms`);
      }
      throw err;
    }
  }

  public async initialize(): Promise<any> {
    const res = await this.postJsonRpc("initialize", {
      protocolVersion: "2025-03-26",
      capabilities: {},
      clientInfo: { name: "raen-ide-extension", version: "1.0.0" },
    });
    return res.result;
  }

  public async listTools(): Promise<any[]> {
    const res = await this.postJsonRpc<{ tools: any[] }>("tools/list", {});
    return res.result?.tools || [];
  }

  public async callTool(name: string, args: Record<string, any>): Promise<McpCallResponse> {
    try {
      const res = await this.postJsonRpc<any>("tools/call", {
        name,
        arguments: args,
      });

      const paymentReceipt = res.headers?.get("x-payment-response") || res.headers?.get("payment-response");

      return {
        ok: true,
        data: res.result,
        receipt: paymentReceipt || "Dev-Key Authorized",
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
