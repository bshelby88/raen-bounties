import { RaenMcpClient } from "./mcpClient.js";
import type { RaenSku } from "./types.js";

export const DEFAULT_CATALOG_URL =
  "https://raw.githubusercontent.com/bshelby88/raen-agent-directory/main/llms.txt";

export class RaenCatalogService {
  private catalogUrl: string;
  private mcpClient: RaenMcpClient;
  private cachedSkus: RaenSku[] | null = null;
  private lastFetch: number = 0;
  private cacheTtlMs: number = 60000; // 1 minute cache

  constructor(catalogUrl: string = DEFAULT_CATALOG_URL, mcpClient?: RaenMcpClient) {
    this.catalogUrl = catalogUrl;
    this.mcpClient = mcpClient || new RaenMcpClient();
  }

  public parseLlmsTxt(content: string): RaenSku[] {
    const lines = content.split("\n");
    const skus: RaenSku[] = [];

    let currentSection = "";

    for (const rawLine of lines) {
      const line = rawLine.trim();

      if (line.startsWith("## ")) {
        currentSection = line.replace(/^##\s+/, "").trim();
        continue;
      }

      // Match "- [name](url): description"
      const match = line.match(/^-\s*\[([^\]]+)\]\(([^)]+)\)\s*:\s*(.+)$/);
      if (match) {
        const [, name, url, description] = match;

        let category: RaenSku["category"] = "fleet-services";
        if (url.includes("workers.dev")) {
          category = "workers";
        } else if (currentSection.includes("Benchmark") || currentSection.includes("Company")) {
          category = "reference";
        }

        // Extract price if mentioned e.g. "$0.05/call" or "$0.10 USDC"
        const priceMatch = description.match(/\$([0-9.]+)(?:\/[a-zA-Z]+|\s*USDC)?/);
        const price = priceMatch ? `$${priceMatch[1]}` : (category === "fleet-services" ? "$0.05" : "Free / Reference");

        skus.push({
          id: name.toLowerCase().replace(/[^a-z0-9_-]/g, "-"),
          name,
          url,
          price,
          category,
          description,
          manifestUrl: url.includes(".fly.dev") || url.includes("workers.dev") ? `${url.replace(/\/+$/, "")}/.well-known/x402.json` : undefined,
        });
      }
    }

    return skus;
  }

  public async fetchCatalog(force: boolean = false): Promise<RaenSku[]> {
    const now = Date.now();
    if (!force && this.cachedSkus && now - this.lastFetch < this.cacheTtlMs) {
      return this.cachedSkus;
    }

    const allSkus: RaenSku[] = [];

    // 1. Fetch MCP gateway tools directly
    try {
      const tools = await this.mcpClient.listTools();
      for (const t of tools) {
        const price = t.description.match(/\$([0-9.]+)/) ? `$${t.description.match(/\$([0-9.]+)/)[1]}` : "$0.05";
        allSkus.push({
          id: t.name,
          name: t.annotations?.title || t.name,
          url: `${this.mcpClient.getGatewayUrl()}#${t.name}`,
          price: `${price} USDC`,
          category: "mcp-tools",
          description: t.description,
          inputSchema: t.inputSchema,
        });
      }
    } catch {
      // If offline, provide standard 5 tools fallback
      const standardTools = [
        { name: "raen_law_lookup", title: "Law Lookup (FCRA/FDCPA)", price: "$0.05 USDC", desc: "US consumer rights citations and statute research." },
        { name: "raen_ticker_analysis", title: "Ticker Consensus Demo", price: "$0.05 USDC", desc: "Synthetic market consensus demo via TradingAgents." },
        { name: "raen_dispute_letter", title: "Dispute Letter Generator", price: "$0.10 USDC", desc: "FCRA dispute letter generation + SVG certificate." },
        { name: "raen_image_generate", title: "NanoBanana Image Gen", price: "$0.01 USDC", desc: "Text-to-image AI generation." },
        { name: "raen_contract_analysis", title: "Contract Analysis", price: "$0.05 USDC", desc: "Contract risk scoring and clause-level review." },
      ];
      for (const st of standardTools) {
        allSkus.push({
          id: st.name,
          name: st.title,
          url: `${this.mcpClient.getGatewayUrl()}#${st.name}`,
          price: st.price,
          category: "mcp-tools",
          description: st.desc,
        });
      }
    }

    // 2. Fetch directory llms.txt
    try {
      const resp = await fetch(this.catalogUrl, { signal: AbortSignal.timeout(10000) });
      if (resp.ok) {
        const text = await resp.text();
        const parsed = this.parseLlmsTxt(text);
        allSkus.push(...parsed);
      }
    } catch {
      // Keep MCP tools if network fetch fails
    }

    this.cachedSkus = allSkus;
    this.lastFetch = now;
    return allSkus;
  }
}
