import type { Action, ActionExample, HandlerCallback, IAgentRuntime, Memory, State } from "../types.js";
import { RaenMcpClient } from "../client.js";

export const toolFinderAction: Action = {
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
  validate: async (_runtime: IAgentRuntime, message: Memory): Promise<boolean> => {
    const text = message.content?.text?.toLowerCase() || "";
    return (
      (text.includes("tool") && (text.includes("find") || text.includes("list") || text.includes("search") || text.includes("what") || text.includes("available"))) ||
      text.includes("raen tools") ||
      text.includes("mcp tools") ||
      text.includes("catalog")
    );
  },
  handler: async (
    runtime: IAgentRuntime,
    message: Memory,
    _state?: State,
    options?: any,
    callback?: HandlerCallback
  ): Promise<boolean> => {
    const apiKey = runtime?.getSetting?.("RAEN_API_KEY") || runtime?.getSetting?.("RAEN_MCP_KEY");
    const client = new RaenMcpClient({ apiKey });

    const query = (options?.query || message.content?.text || "").toLowerCase();

    try {
      const tools = await client.listTools();

      // Filter by query if query is specific
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
    } catch (err: any) {
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
    [
      {
        user: "user",
        content: { text: "List all tools available on the RAEN MCP gateway." },
      },
      {
        user: "assistant",
        content: {
          text: "Fetching active tool registry from https://raen-mcp-gateway.fly.dev/mcp.",
          action: "TOOL_FINDER",
        },
      },
    ],
  ] as ActionExample[][],
};
