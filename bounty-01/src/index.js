/**
 * BOUNTY-01: ElizaOS Plugin for the RAEN MCP Gateway
 * Connects an ElizaOS agent to https://raen-mcp-gateway.fly.dev/mcp (Streamable HTTP, Bearer key)
 * and exposes law_lookup, dispute_letter, image_generate, contract_analyze, and tool_finder as actions.
 */

export const DEFAULT_RAEN_MCP_URL = 'https://raen-mcp-gateway.fly.dev/mcp';

export const ACTION_SPECS = [
  {
    name: 'LAW_LOOKUP',
    mcpTool: 'law_lookup',
    description: 'Look up federal or state statutory law, regulations, and case-law citations via the RAEN MCP gateway.',
    similes: ['SEARCH_LAW', 'STATUTE_LOOKUP', 'LEGAL_RESEARCH'],
  },
  {
    name: 'DISPUTE_LETTER',
    mcpTool: 'dispute_letter',
    description: 'Draft a formal consumer, billing, FCRA, or contract dispute letter via the RAEN MCP gateway.',
    similes: ['DRAFT_DISPUTE_LETTER', 'GENERATE_DISPUTE_NOTICE'],
  },
  {
    name: 'IMAGE_GENERATE',
    mcpTool: 'image_generate',
    description: 'Generate an illustration or visual asset from a text prompt via the RAEN MCP gateway.',
    similes: ['CREATE_IMAGE', 'RENDER_IMAGE'],
  },
  {
    name: 'CONTRACT_ANALYZE',
    mcpTool: 'contract_analyze',
    description: 'Analyze contract clauses, risks, obligations, and termination terms via the RAEN MCP gateway.',
    similes: ['REVIEW_CONTRACT', 'AUDIT_AGREEMENT'],
  },
  {
    name: 'TOOL_FINDER',
    mcpTool: 'tool_finder',
    description: 'Discover and rank available x402 and RAEN MCP tools matching a task description.',
    similes: ['FIND_MCP_TOOL', 'DISCOVER_RAEN_TOOLS'],
  },
];

export function resolveApiKey(runtime) {
  if (runtime && typeof runtime.getSetting === 'function') {
    const val = runtime.getSetting('RAEN_MCP_API_KEY');
    if (val) return val;
  }
  return process.env.RAEN_MCP_API_KEY || '';
}

export function resolveGatewayUrl(runtime) {
  if (runtime && typeof runtime.getSetting === 'function') {
    const val = runtime.getSetting('RAEN_MCP_URL');
    if (val) return val;
  }
  return process.env.RAEN_MCP_URL || DEFAULT_RAEN_MCP_URL;
}

export async function callRaenMcpTool({
  toolName,
  args,
  apiKey,
  gatewayUrl = DEFAULT_RAEN_MCP_URL,
  fetchImpl = globalThis.fetch,
}) {
  if (!apiKey || !String(apiKey).trim()) {
    throw new Error('Missing RAEN_MCP_API_KEY for RAEN MCP gateway authentication');
  }
  const rpcPayload = {
    jsonrpc: '2.0',
    id: `raen-${toolName}-${Date.now()}`,
    method: 'tools/call',
    params: {
      name: toolName,
      arguments: args || {},
    },
  };

  const response = await fetchImpl(gatewayUrl, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json, text/event-stream',
      Authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify(rpcPayload),
  });

  if (!response.ok) {
    throw new Error(`RAEN MCP gateway HTTP ${response.status}`);
  }

  const contentType = (response.headers?.get?.('content-type') || '').toLowerCase();
  const rawText = await response.text();
  let parsed;
  if (contentType.includes('text/event-stream')) {
    const dataLine = rawText
      .split('\n')
      .map((l) => l.trim())
      .find((l) => l.startsWith('data:'));
    parsed = JSON.parse(dataLine ? dataLine.slice(5).trim() : rawText);
  } else {
    parsed = JSON.parse(rawText);
  }

  if (parsed.error) {
    throw new Error(`RAEN MCP error: ${parsed.error.message || JSON.stringify(parsed.error)}`);
  }

  const contentBlocks = parsed.result?.content || [];
  const textOut = contentBlocks
    .filter((c) => c && c.type === 'text')
    .map((c) => c.text)
    .join('\n') || JSON.stringify(parsed.result ?? parsed);

  return {
    tool: toolName,
    raw: parsed.result ?? parsed,
    text: textOut,
  };
}

export function createRaenAction(spec, options = {}) {
  return {
    name: spec.name,
    similes: spec.similes,
    description: spec.description,
    validate: async (runtime) => {
      const key = options.apiKey || resolveApiKey(runtime);
      return Boolean(key && String(key).trim().length > 0);
    },
    handler: async (runtime, message, state, _opts, callback) => {
      const apiKey = options.apiKey || resolveApiKey(runtime);
      const gatewayUrl = options.gatewayUrl || resolveGatewayUrl(runtime);
      const fetchImpl = options.fetchImpl || globalThis.fetch;

      const content = message?.content || {};
      const args = content.arguments || {
        query: content.text || '',
        ...(state?.raenArgs || {}),
      };

      const res = await callRaenMcpTool({
        toolName: spec.mcpTool,
        args,
        apiKey,
        gatewayUrl,
        fetchImpl,
      });

      if (typeof callback === 'function') {
        await callback({
          text: res.text,
          action: spec.name,
          data: res.raw,
        });
      }
      return res;
    },
    examples: [
      [
        {
          user: '{{user1}}',
          content: { text: `Run ${spec.mcpTool} via RAEN MCP gateway` },
        },
        {
          user: '{{agentName}}',
          content: {
            text: `Completed ${spec.mcpTool} via RAEN MCP gateway.`,
            action: spec.name,
          },
        },
      ],
    ],
  };
}

export function createRaenMcpPlugin(options = {}) {
  return {
    name: 'raen-mcp-gateway',
    description: 'ElizaOS plugin for the RAEN MCP Gateway (law_lookup, dispute_letter, image_generate, contract_analyze, tool_finder)',
    actions: ACTION_SPECS.map((spec) => createRaenAction(spec, options)),
  };
}

export const raenMcpPlugin = createRaenMcpPlugin();
export default raenMcpPlugin;
