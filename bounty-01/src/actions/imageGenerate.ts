import type { Action, ActionExample, HandlerCallback, IAgentRuntime, Memory, State } from "../types.js";
import { RaenMcpClient } from "../client.js";

export const imageGenerateAction: Action = {
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
  validate: async (_runtime: IAgentRuntime, message: Memory): Promise<boolean> => {
    const text = message.content?.text?.toLowerCase() || "";
    return (
      text.includes("generate an image") ||
      text.includes("create an image") ||
      text.includes("draw") ||
      text.includes("illustration") ||
      (text.includes("image") && (text.includes("prompt") || text.includes("picture") || text.includes("render")))
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
  ] as ActionExample[][],
};
