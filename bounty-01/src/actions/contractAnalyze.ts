import type { Action, ActionExample, HandlerCallback, IAgentRuntime, Memory, State } from "../types.js";
import { RaenMcpClient } from "../client.js";

export const contractAnalyzeAction: Action = {
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
  validate: async (_runtime: IAgentRuntime, message: Memory): Promise<boolean> => {
    const text = message.content?.text?.toLowerCase() || "";
    return (
      (text.includes("contract") && (text.includes("analyze") || text.includes("review") || text.includes("audit") || text.includes("risk"))) ||
      text.includes("terms of service") ||
      text.includes("indemnity clause") ||
      text.includes("nda review")
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
  ] as ActionExample[][],
};
