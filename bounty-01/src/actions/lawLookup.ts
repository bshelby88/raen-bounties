import type { Action, ActionExample, HandlerCallback, IAgentRuntime, Memory, State } from "../types.js";
import { RaenMcpClient } from "../client.js";

export const lawLookupAction: Action = {
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
  validate: async (_runtime: IAgentRuntime, message: Memory): Promise<boolean> => {
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
  handler: async (
    runtime: IAgentRuntime,
    message: Memory,
    _state?: State,
    options?: any,
    callback?: HandlerCallback
  ): Promise<boolean> => {
    const apiKey = runtime?.getSetting?.("RAEN_API_KEY") || runtime?.getSetting?.("RAEN_MCP_KEY");
    const client = new RaenMcpClient({ apiKey });

    // Extract topic
    let topic = options?.topic;
    if (!topic) {
      const rawText = message.content?.text || "";
      // Strip common trigger prefixes
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
    [
      {
        user: "user",
        content: { text: "Look up FCRA permissible purpose requirements for running a background check." },
      },
      {
        user: "assistant",
        content: {
          text: "Querying RAEN Law Lookup for 15 U.S.C. § 1681b permissible purpose provisions.",
          action: "LAW_LOOKUP",
        },
      },
    ],
  ] as ActionExample[][],
};
