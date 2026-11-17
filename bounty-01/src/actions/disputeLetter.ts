import type { Action, ActionExample, HandlerCallback, IAgentRuntime, Memory, State } from "../types.js";
import { RaenMcpClient } from "../client.js";

export const disputeLetterAction: Action = {
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
  validate: async (_runtime: IAgentRuntime, message: Memory): Promise<boolean> => {
    const text = message.content?.text?.toLowerCase() || "";
    return (
      (text.includes("dispute") && (text.includes("letter") || text.includes("credit") || text.includes("debt"))) ||
      text.includes("remove collection") ||
      text.includes("inaccurate reporting")
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
  ] as ActionExample[][],
};
