export * from "./lawLookup.js";
export * from "./disputeLetter.js";
export * from "./imageGenerate.js";
export * from "./contractAnalyze.js";
export * from "./toolFinder.js";

import { lawLookupAction } from "./lawLookup.js";
import { disputeLetterAction } from "./disputeLetter.js";
import { imageGenerateAction } from "./imageGenerate.js";
import { contractAnalyzeAction } from "./contractAnalyze.js";
import { toolFinderAction } from "./toolFinder.js";

export const allActions = [
  lawLookupAction,
  disputeLetterAction,
  imageGenerateAction,
  contractAnalyzeAction,
  toolFinderAction,
];
