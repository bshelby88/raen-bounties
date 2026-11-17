export interface RaenSku {
  id: string;
  name: string;
  url: string;
  price: string;
  category: "mcp-tools" | "fleet-services" | "workers" | "reference";
  description: string;
  manifestUrl?: string;
  inputSchema?: any;
}

export interface McpCallResponse {
  ok: boolean;
  data?: any;
  error?: string;
  paymentRequired?: boolean;
  challenge?: any;
  receipt?: any;
}

export interface CursorMcpConfig {
  mcpServers: {
    raen?: {
      url: string;
      headers?: {
        Authorization?: string;
      };
    };
  };
}
