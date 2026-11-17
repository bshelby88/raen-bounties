/**
 * @elizaos/plugin-raen
 * ElizaOS plugin for the RAEN fleet MCP Gateway
 */
import type { Plugin } from "./types.js";
import {
  allActions,
  lawLookupAction,
  disputeLetterAction,
  imageGenerateAction,
  contractAnalyzeAction,
  toolFinderAction,
} from "./actions/index.js";

export * from "./types.js";
export * from "./client.js";
export * from "./actions/index.js";

export const raenPlugin: Plugin = {
  name: "raen",
  description:
    "RAEN MCP Gateway plugin for ElizaOS: integrates paid and discovery tools for legal research (FCRA/FDCPA), dispute letters (Dispute-Forge), AI image generation, contract analysis (Contract-Eye), and tool discovery.",
  actions: allActions,
};

export default raenPlugin;
