# `@raen/plugin-mcp-gateway` — ElizaOS Plugin for RAEN MCP Gateway (BOUNTY-01)

ElizaOS plugin (TypeScript / ES Module) connecting an ElizaOS agent to the **RAEN MCP Gateway** (`https://raen-mcp-gateway.fly.dev/mcp`, Streamable HTTP JSON-RPC 2.0, Bearer authentication) and exposing all 5 gateway tools as first-class ElizaOS `Action`s:

- `LAW_LOOKUP` (`law_lookup`)
- `DISPUTE_LETTER` (`dispute_letter`)
- `IMAGE_GENERATE` (`image_generate`)
- `CONTRACT_ANALYZE` (`contract_analyze`)
- `TOOL_FINDER` (`tool_finder`)

## Installation & Configuration

```bash
export RAEN_MCP_API_KEY="your_raen_mcp_bearer_key"
export RAEN_MCP_URL="https://raen-mcp-gateway.fly.dev/mcp"
```

Register `raenMcpPlugin` in your ElizaOS `AgentRuntime` character configuration:

```ts
import { raenMcpPlugin } from '@raen/plugin-mcp-gateway';

export const character = {
  name: 'RaenLegalAgent',
  plugins: [raenMcpPlugin],
};
```

## End-to-End `law_lookup` Demo & Transcript

```bash
node bounty-01/demo/law-lookup-demo.mjs
```

```json
{
  "demo": "LAW_LOOKUP",
  "transcript": [
    {
      "text": "15 U.S.C. § 1681i (FCRA Section 611): Consumer reporting agencies must conduct a reasonable reinvestigation within 30 days of receiving notice of a consumer dispute.",
      "action": "LAW_LOOKUP",
      "data": {
        "content": [
          {
            "type": "text",
            "text": "15 U.S.C. § 1681i (FCRA Section 611): Consumer reporting agencies must conduct a reasonable reinvestigation within 30 days of receiving notice of a consumer dispute."
          }
        ]
      }
    }
  ]
}
```
