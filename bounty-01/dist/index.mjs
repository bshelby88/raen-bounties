/**
 * RaenMcpClient: High-performance streamable HTTP client for the RAEN MCP Gateway
 */
export const DEFAULT_GATEWAY_URL = "https://raen-mcp-gateway.fly.dev/mcp";
export const DEFAULT_TIMEOUT_MS = 25000;

export class RaenMcpClient {
  constructor(config = {}) {
    this.gatewayUrl = (config.gatewayUrl || process.env.RAEN_GATEWAY_URL || DEFAULT_GATEWAY_URL).replace(/\/+$/, "");
    this.apiKey = config.apiKey || process.env.RAEN_API_KEY || process.env.RAEN_MCP_KEY;
    this.timeoutMs = config.timeoutMs || DEFAULT_TIMEOUT_MS;
    this.requestId = 1;
  }

  getApiKey() {
    return this.apiKey;
  }

  setApiKey(key) {
    this.apiKey = key;
  }

  getGatewayUrl() {
    return this.gatewayUrl;
  }

  async postJsonRpc(method, params = {}) {
    const id = this.requestId++;
    const body = JSON.stringify({
      jsonrpc: "2.0",
      id,
      method,
      params,
    });

    const headers = {
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

      if (resp.status === 402) {
        const errorData = await resp.json().catch(() => ({}));
        const err = new Error(
          `x402 Payment Required: ${errorData?.error || "Payment required to execute paid MCP tool"}`
        );
        err.status = 402;
        err.challenge = errorData;
        throw err;
      }

      if (resp.status === 401 || resp.status === 403) {
        throw new Error(`Authentication failed (${resp.status}): Invalid or missing RAEN Bearer dev key.`);
      }

      if (!resp.ok) {
        const text = await resp.text().catch(() => "");
        throw new Error(`Gateway returned HTTP ${resp.status}: ${text}`);
      }

      const json = await resp.json();
      if (json.error) {
        throw new Error(`MCP Error [${json.error.code}]: ${json.error.message}`);
      }

      return json.result;
    } catch (err) {
      clearTimeout(timeout);
      if (err.name === "AbortError") {
        throw new Error(`Gateway request timed out after ${this.timeoutMs}ms`);
      }
      throw err;
    }
  }

  async initialize() {
    return this.postJsonRpc("initialize", {
      protocolVersion: "2025-03-26",
      capabilities: {},
      clientInfo: {
        name: "@elizaos/plugin-raen",
        version: "1.0.0",
      },
    });
  }

  async listTools() {
    const res = await this.postJsonRpc("tools/list", {});
    return res?.tools || [];
  }

  async callTool(name, args) {
    try {
      const res = await this.postJsonRpc("tools/call", {
        name,
        arguments: args,
      });
      return {
        ok: true,
        data: res,
      };
    } catch (err) {
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

export const lawLookupAction = {
  name: "LAW_LOOKUP",
  similes: [
    "LEGAL_RESEARCH",
    "CONSUMER_RIGHTS_LOOKUP",
    "FCRA_LOOKUP",
    "FDCPA_LOOKUP",
    "TILA_LOOKUP",
    "STATE_UDAP",
  ],
  description:
    "Look up US consumer-protection law citations (FCRA, FDCPA, TILA, state UDAP) on a topic. Returns formal citations, plain-English summaries, reporting timelines, and statutes of limitations.",
  validate: async (_runtime, message) => {
    const text = message.content?.text?.toLowerCase() || "";
    return (
      text.includes("law") ||
      text.includes("fcra") ||
      text.includes("fdcpa") ||
      text.includes("tila") ||
      text.includes("statute") ||
      text.includes("debt") ||
      text.includes("credit report") ||
      text.includes("citation")
    );
  },
  handler: async (runtime, message, _state, options, callback) => {
    const apiKey = runtime?.getSetting?.("RAEN_API_KEY") || runtime?.getSetting?.("RAEN_MCP_KEY");
    const client = new RaenMcpClient({ apiKey });

    let topic = options?.topic;
    if (!topic) {
      const rawText = message.content?.text || "";
      topic = rawText
        .replace(/^(please\s+)?(look\s*up|search|find|cite)\s+(the\s+)?(law|statute|citation|info\s+on)?/i, "")
        .trim();
      if (!topic || topic.length < 3) {
        topic = rawText;
      }
    }

    const result = await client.callTool("raen_law_lookup", { topic });

    if (!result.ok) {
      const errorMsg = result.paymentRequired
        ? `x402 Payment Required: $0.05 USDC needed to execute law lookup on Base mainnet. Set RAEN_API_KEY with a valid dev key.`
        : `Law lookup failed: ${result.error}`;
      if (callback) {
        await callback({ text: errorMsg, action: "LAW_LOOKUP_ERROR", content: result });
      }
      return false;
    }

    const formatted =
      typeof result.data === "string"
        ? result.data
        : JSON.stringify(result.data?.content || result.data, null, 2);

    if (callback) {
      await callback({
        text: `### Legal Citation Research: "${topic}"\n\n${formatted}`,
        action: "LAW_LOOKUP_RESPONSE",
        content: result.data,
      });
    }

    return true;
  },
  examples: [
    [
      {
        user: "user",
        content: { text: "What are the rules regarding debt collection calls at work under the FDCPA?" },
      },
      {
        user: "assistant",
        content: {
          text: "Let me consult the RAEN Law Lookup database for FDCPA workplace contact citations.",
          action: "LAW_LOOKUP",
        },
      },
    ],
  ],
};

export const disputeLetterAction = {
  name: "DISPUTE_LETTER",
  similes: [
    "CREDIT_DISPUTE",
    "COLLECTIONS_DISPUTE",
    "FCRA_DISPUTE_LETTER",
    "GENERATE_DISPUTE",
    "DEBT_DISPUTE",
  ],
  description:
    "Generate an FCRA-compliant credit dispute letter plus an SVG certificate of dispute (Dispute-Forge).",
  validate: async (_runtime, message) => {
    const text = message.content?.text?.toLowerCase() || "";
    return (
      (text.includes("dispute") && (text.includes("letter") || text.includes("credit") || text.includes("debt"))) ||
      text.includes("remove collection") ||
      text.includes("inaccurate reporting")
    );
  },
  handler: async (runtime, message, _state, options, callback) => {
    const apiKey = runtime?.getSetting?.("RAEN_API_KEY") || runtime?.getSetting?.("RAEN_MCP_KEY");
    const client = new RaenMcpClient({ apiKey });

    const creditor = options?.creditor || "Creditor / Bureau";
    const reason = options?.reason || message.content?.text || "Inaccurate account details and reporting dispute";

    const result = await client.callTool("raen_dispute_letter", { creditor, reason });

    if (!result.ok) {
      const errorMsg = result.paymentRequired
        ? `x402 Payment Required: $0.10 USDC needed to generate dispute letter on Base mainnet. Set RAEN_API_KEY with a valid dev key.`
        : `Dispute letter generation failed: ${result.error}`;
      if (callback) {
        await callback({ text: errorMsg, action: "DISPUTE_LETTER_ERROR", content: result });
      }
      return false;
    }

    const formatted =
      typeof result.data === "string"
        ? result.data
        : JSON.stringify(result.data?.content || result.data, null, 2);

    if (callback) {
      await callback({
        text: `### Dispute Letter Generated (Dispute-Forge)\n\n**Creditor:** ${creditor}\n**Reason:** ${reason}\n\n${formatted}`,
        action: "DISPUTE_LETTER_RESPONSE",
        content: result.data,
      });
    }

    return true;
  },
  examples: [
    [
      {
        user: "user",
        content: { text: "Draft a formal dispute letter to Midland Credit for an inaccurate collection." },
      },
      {
        user: "assistant",
        content: {
          text: "Generating FCRA-compliant dispute package with dispute certificate via RAEN Dispute-Forge.",
          action: "DISPUTE_LETTER",
        },
      },
    ],
  ],
};

export const imageGenerateAction = {
  name: "IMAGE_GENERATE",
  similes: [
    "GENERATE_IMAGE",
    "CREATE_IMAGE",
    "TEXT_TO_IMAGE",
    "AI_IMAGE",
    "DRAW_IMAGE",
  ],
  description:
    "Generate an AI image from a text prompt (Gemini upstream). Returns base64 PNG metadata/JSON.",
  validate: async (_runtime, message) => {
    const text = message.content?.text?.toLowerCase() || "";
    return (
      text.includes("generate an image") ||
      text.includes("create an image") ||
      text.includes("draw") ||
      text.includes("illustration") ||
      (text.includes("image") && (text.includes("prompt") || text.includes("picture") || text.includes("render")))
    );
  },
  handler: async (runtime, message, _state, options, callback) => {
    const apiKey = runtime?.getSetting?.("RAEN_API_KEY") || runtime?.getSetting?.("RAEN_MCP_KEY");
    const client = new RaenMcpClient({ apiKey });

    const rawText = message.content?.text || "";
    const prompt =
      options?.prompt ||
      rawText.replace(/^(please\s+)?(generate|create|render|make|draw)\s+(an?\s+)?(image|picture|photo)\s+(of\s+)?/i, "").trim() ||
      rawText;
    const aspectRatio = options?.aspectRatio || "1:1";

    const result = await client.callTool("raen_image_generate", { prompt, aspectRatio });

    if (!result.ok) {
      const errorMsg = result.paymentRequired
        ? `x402 Payment Required: $0.01 USDC needed to generate image on Base mainnet. Set RAEN_API_KEY with a valid dev key.`
        : `Image generation failed: ${result.error}`;
      if (callback) {
        await callback({ text: errorMsg, action: "IMAGE_GENERATE_ERROR", content: result });
      }
      return false;
    }

    if (callback) {
      await callback({
        text: `### Image Generated: "${prompt}" (Aspect Ratio: ${aspectRatio})\n\nImage metadata received successfully from RAEN image service.`,
        action: "IMAGE_GENERATE_RESPONSE",
        content: result.data,
      });
    }

    return true;
  },
  examples: [
    [
      {
        user: "user",
        content: { text: "Generate an image of a cybernetic courtroom with holographic legal scales." },
      },
      {
        user: "assistant",
        content: {
          text: "Dispatching prompt to RAEN NanoBanana image generator via MCP.",
          action: "IMAGE_GENERATE",
        },
      },
    ],
  ],
};

export const contractAnalyzeAction = {
  name: "CONTRACT_ANALYZE",
  similes: [
    "AUDIT_CONTRACT",
    "REVIEW_CONTRACT",
    "ANALYZE_AGREEMENT",
    "FLAG_CLAUSES",
    "CONTRACT_RISK",
  ],
  description:
    "Analyze contract text for risky, one-sided, or unusual clauses. Returns a risk score and flagged clauses with severity, explanation, and suggested edits (Contract-Eye).",
  validate: async (_runtime, message) => {
    const text = message.content?.text?.toLowerCase() || "";
    return (
      (text.includes("contract") && (text.includes("analyze") || text.includes("review") || text.includes("audit") || text.includes("risk"))) ||
      text.includes("terms of service") ||
      text.includes("indemnity clause") ||
      text.includes("nda review")
    );
  },
  handler: async (runtime, message, _state, options, callback) => {
    const apiKey = runtime?.getSetting?.("RAEN_API_KEY") || runtime?.getSetting?.("RAEN_MCP_KEY");
    const client = new RaenMcpClient({ apiKey });

    const contractText = options?.text || message.content?.text || "";
    if (contractText.length < 40) {
      if (callback) {
        await callback({
          text: "Contract analysis requires at least 40 characters of contract text to review.",
          action: "CONTRACT_ANALYZE_ERROR",
        });
      }
      return false;
    }

    const focus = options?.focus || ["indemnity", "liability", "termination", "jurisdiction"];

    const result = await client.callTool("raen_contract_analysis", { text: contractText, focus });

    if (!result.ok) {
      const errorMsg = result.paymentRequired
        ? `x402 Payment Required: $0.05 USDC needed to analyze contract on Base mainnet. Set RAEN_API_KEY with a valid dev key.`
        : `Contract analysis failed: ${result.error}`;
      if (callback) {
        await callback({ text: errorMsg, action: "CONTRACT_ANALYZE_ERROR", content: result });
      }
      return false;
    }

    const formatted =
      typeof result.data === "string"
        ? result.data
        : JSON.stringify(result.data?.content || result.data, null, 2);

    if (callback) {
      await callback({
        text: `### Contract Audit Report (Contract-Eye)\n\n${formatted}`,
        action: "CONTRACT_ANALYZE_RESPONSE",
        content: result.data,
      });
    }

    return true;
  },
  examples: [
    [
      {
        user: "user",
        content: { text: "Audit this agreement text: The Contractor shall indemnify, defend and hold harmless the Company from any claims without limitation." },
      },
      {
        user: "assistant",
        content: {
          text: "Submitting contract text to RAEN Contract-Eye risk analyzer.",
          action: "CONTRACT_ANALYZE",
        },
      },
    ],
  ],
};

export const toolFinderAction = {
  name: "TOOL_FINDER",
  similes: [
    "DISCOVER_TOOLS",
    "FIND_TOOL",
    "LIST_RAEN_TOOLS",
    "RAEN_CATALOG",
    "BROWSE_RAEN_TOOLS",
  ],
  description:
    "Discover and search available RAEN fleet tools, schemas, and per-call micro-pricing from the live MCP gateway.",
  validate: async (_runtime, message) => {
    const text = message.content?.text?.toLowerCase() || "";
    return (
      (text.includes("tool") && (text.includes("find") || text.includes("list") || text.includes("search") || text.includes("what") || text.includes("available"))) ||
      text.includes("raen tools") ||
      text.includes("mcp tools") ||
      text.includes("catalog")
    );
  },
  handler: async (runtime, message, _state, options, callback) => {
    const apiKey = runtime?.getSetting?.("RAEN_API_KEY") || runtime?.getSetting?.("RAEN_MCP_KEY");
    const client = new RaenMcpClient({ apiKey });

    const query = (options?.query || message.content?.text || "").toLowerCase();

    try {
      const tools = await client.listTools();

      const isGeneric =
        query.includes("what tools") ||
        query.includes("list tools") ||
        query.includes("all tools") ||
        query.includes("available tools");

      const filtered = isGeneric
        ? tools
        : tools.filter(
            (t) =>
              t.name.toLowerCase().includes(query) ||
              t.description.toLowerCase().includes(query) ||
              t.annotations?.title?.toLowerCase().includes(query)
          );

      const displayList = filtered.length > 0 ? filtered : tools;

      const lines = [
        "### Available RAEN MCP Gateway Tools",
        "",
        "| Tool Name | Title | Description | Schema Required |",
        "|---|---|---|---|",
      ];

      for (const t of displayList) {
        const title = t.annotations?.title || t.name;
        const required = t.inputSchema?.required ? t.inputSchema.required.join(", ") : "none";
        lines.push(`| \`${t.name}\` | **${title}** | ${t.description} | \`${required}\` |`);
      }

      const summaryText = lines.join("\n");

      if (callback) {
        await callback({
          text: summaryText,
          action: "TOOL_FINDER_RESPONSE",
          content: { tools: displayList },
        });
      }

      return true;
    } catch (err) {
      const errorMsg = `Failed to fetch RAEN tools from MCP gateway: ${err.message}`;
      if (callback) {
        await callback({ text: errorMsg, action: "TOOL_FINDER_ERROR" });
      }
      return false;
    }
  },
  examples: [
    [
      {
        user: "user",
        content: { text: "What RAEN MCP tools are available to help with legal research or contract review?" },
      },
      {
        user: "assistant",
        content: {
          text: "Querying RAEN MCP Gateway for registered tools matching legal research and contract review.",
          action: "TOOL_FINDER",
        },
      },
    ],
  ],
};

export const allActions = [
  lawLookupAction,
  disputeLetterAction,
  imageGenerateAction,
  contractAnalyzeAction,
  toolFinderAction,
];

export const raenPlugin = {
  name: "raen",
  description:
    "RAEN MCP Gateway plugin for ElizaOS: integrates paid and discovery tools for legal research (FCRA/FDCPA), dispute letters (Dispute-Forge), AI image generation, contract analysis (Contract-Eye), and tool discovery.",
  actions: allActions,
};

export default raenPlugin;
