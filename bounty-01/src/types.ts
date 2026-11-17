/**
 * Type definitions for @elizaos/plugin-raen
 */

export interface RaenPluginConfig {
  apiKey?: string;
  gatewayUrl?: string;
  timeoutMs?: number;
}

export interface McpToolSchema {
  name: string;
  description: string;
  inputSchema: {
    type: string;
    properties?: Record<string, any>;
    required?: string[];
  };
  annotations?: {
    title?: string;
    readOnlyHint?: boolean;
    destructiveHint?: boolean;
    idempotentHint?: boolean;
    openWorldHint?: boolean;
  };
}

export interface McpCallResult {
  ok: boolean;
  data?: any;
  error?: string;
  paymentRequired?: boolean;
  challenge?: any;
}

// Minimal ElizaOS type abstractions for zero-dependency portability
export interface Memory {
  id?: string;
  userId?: string;
  agentId?: string;
  roomId?: string;
  content: {
    text: string;
    action?: string;
    source?: string;
    attachments?: any[];
    [key: string]: any;
  };
  createdAt?: number;
}

export interface State {
  [key: string]: any;
}

export interface IAgentRuntime {
  getSetting(key: string): string | undefined;
  [key: string]: any;
}

export type HandlerCallback = (response: {
  text: string;
  action?: string;
  content?: any;
}) => Promise<any> | any;

export interface ActionExample {
  user: string;
  content: {
    text: string;
    action?: string;
    [key: string]: any;
  };
}

export interface Action {
  name: string;
  similes: string[];
  description: string;
  validate: (runtime: IAgentRuntime, message: Memory, state?: State) => Promise<boolean>;
  handler: (
    runtime: IAgentRuntime,
    message: Memory,
    state?: State,
    options?: any,
    callback?: HandlerCallback
  ) => Promise<boolean>;
  examples: ActionExample[][];
}

export interface Plugin {
  name: string;
  description: string;
  actions: Action[];
  evaluators?: any[];
  providers?: any[];
  services?: any[];
}
