# @elizaos/plugin-raen (BOUNTY-01)

ElizaOS plugin that connects an autonomous ElizaOS agent to the **RAEN MCP Gateway** (`https://raen-mcp-gateway.fly.dev/mcp`) via standard JSON-RPC 2.0 over streamable HTTP with Bearer key authentication.

Exposes 5 production actions covering the RAEN x402 fleet:
1. `LAW_LOOKUP`: US consumer-rights law research & citations (FCRA, FDCPA, TILA, state UDAP).
2. `DISPUTE_LETTER`: Credit dispute letter generation + SVG certificate of dispute (Dispute-Forge).
3. `IMAGE_GENERATE`: AI image generation from text prompt (NanoBanana / Gemini).
4. `CONTRACT_ANALYZE`: Contract risk scoring and clause-level audit (Contract-Eye).
5. `TOOL_FINDER`: Dynamic MCP tool and fleet capability discovery directly from the gateway registry.

---

## Architecture

```
ElizaOS Agent Runtime
       │
       ▼
[@elizaos/plugin-raen]
       │
       ├── lawLookupAction      ──► raen_law_lookup
       ├── disputeLetterAction  ──► raen_dispute_letter
       ├── imageGenerateAction  ──► raen_image_generate
       ├── contractAnalyzeAction──► raen_contract_analysis
       └── toolFinderAction     ──► tools/list
       │
       ▼
RaenMcpClient (JSON-RPC 2.0 / Native fetch)
       │ (Authorization: Bearer <RAEN_API_KEY>)
       ▼
https://raen-mcp-gateway.fly.dev/mcp
```

---

## Installation & Setup

In your ElizaOS project:

```bash
# Using npm
npm install ./bounty-01

# Or with pnpm
pnpm add ./bounty-01
```

### Configuration

Add your RAEN MCP dev key to your `.env` or agent character configuration:

```env
RAEN_API_KEY=your_raen_mcp_bearer_key
```

> **Obtaining a Dev Key:** Free 30-day developer keys can be requested via self-serve:
> ```bash
> curl -X POST https://raen-mcp-gateway.fly.dev/keys/request \
>   -H "Content-Type: application/json" \
>   -d '{"email":"your-email@domain.com"}'
> ```

---

## Registering with ElizaOS

Import and register `raenPlugin` in your ElizaOS character file or runtime setup:

```typescript
import { AgentRuntime } from "@elizaos/core";
import { raenPlugin } from "@elizaos/plugin-raen";

const runtime = new AgentRuntime({
  // ... character config
  plugins: [raenPlugin],
});
```

---

## Actions Reference

### 1. `LAW_LOOKUP`
- **Similes:** `LEGAL_RESEARCH`, `CONSUMER_RIGHTS_LOOKUP`, `FCRA_LOOKUP`, `FDCPA_LOOKUP`, `TILA_LOOKUP`, `STATE_UDAP`
- **Description:** Queries formal statutes, plain-English summaries, reporting timelines, and statutes of limitations for US consumer protection law.
- **Example:** *"What are the permissible purposes for pulling a credit report under FCRA § 604?"*

### 2. `DISPUTE_LETTER`
- **Similes:** `CREDIT_DISPUTE`, `COLLECTIONS_DISPUTE`, `FCRA_DISPUTE_LETTER`, `GENERATE_DISPUTE`
- **Description:** Generates an FCRA-compliant credit dispute letter and an SVG verification certificate.
- **Example:** *"Draft a formal dispute letter to Midland Credit for an inaccurate debt entry."*

### 3. `IMAGE_GENERATE`
- **Similes:** `GENERATE_IMAGE`, `CREATE_IMAGE`, `TEXT_TO_IMAGE`, `AI_IMAGE`
- **Description:** Generates AI images from text prompts (supports aspect ratios: `1:1`, `16:9`, `9:16`, `3:2`, etc.).
- **Example:** *"Generate an image of a cybernetic courtroom with holographic legal scales."*

### 4. `CONTRACT_ANALYZE`
- **Similes:** `AUDIT_CONTRACT`, `REVIEW_CONTRACT`, `ANALYZE_AGREEMENT`, `FLAG_CLAUSES`
- **Description:** Audits contract text for liability, indemnity, termination, and one-sided clauses, returning structured severity ratings.
- **Example:** *"Analyze this contract snippet for one-sided indemnity obligations."*

### 5. `TOOL_FINDER`
- **Similes:** `DISCOVER_TOOLS`, `FIND_TOOL`, `LIST_RAEN_TOOLS`, `RAEN_CATALOG`
- **Description:** Dynamically queries the RAEN MCP gateway via JSON-RPC `tools/list` to report active tools, schemas, and pricing.
- **Example:** *"What RAEN tools are available to help with contract audits?"*

---

## Running Unit Tests

The test suite runs using Node's native test runner (zero external test runner dependencies):

```bash
cd bounty-01
npm test
```

### Test Output

```
▶ RAEN ElizaOS Plugin Structure
  ✔ exports valid ElizaOS Plugin object with metadata (6.6502ms)
  ✔ exposes all 5 required BOUNTY-01 actions (0.903ms)
  ✔ conforms to ElizaOS Action interface for all actions (0.9273ms)
✔ RAEN ElizaOS Plugin Structure (92.8423ms)
▶ Action Validation & Trigger Matching
  ✔ lawLookupAction validates legal and regulatory triggers (1.8266ms)
  ✔ disputeLetterAction validates dispute requests (1.3405ms)
  ✔ imageGenerateAction validates generation requests (0.967ms)
  ✔ contractAnalyzeAction validates contract review requests (1.5334ms)
  ✔ toolFinderAction validates tool discovery requests (2.184ms)
✔ Action Validation & Trigger Matching (10.354ms)
▶ RaenMcpClient & JSON-RPC Protocol
  ✔ initializes with default gateway and config (1.6185ms)
  ✔ correctly handles 402 payment challenge responses (265.9183ms)
  ✔ handles successful JSON-RPC tool responses (3.6369ms)
✔ RaenMcpClient & JSON-RPC Protocol (272.5759ms)
ℹ tests 11
ℹ suites 3
ℹ pass 11
ℹ fail 0
```

---

## Live Gateway Demo & Verification Transcript

Run the included live demo:

```bash
node bounty-01/demo/law-lookup-demo.mjs
```

### Live Transcript against `https://raen-mcp-gateway.fly.dev/mcp`

```
==================================================================
  ELIZAOS RAEN PLUGIN — LIVE MCP GATEWAY DEMO
==================================================================

[1] Connecting to MCP Gateway at: https://raen-mcp-gateway.fly.dev/mcp
[!] Running in unauthenticated mode (set RAEN_API_KEY to execute paid tool calls)

[2] Initializing MCP protocol handshake (JSON-RPC initialize)...
    Handshake Success!
    Server Name   : raen-mcp
    Server Version: 1.0.0
    Protocol Ver  : 2025-03-26
    Instructions  : RAEN paid x402 services. Each tool call spends USDC on Base via the x402 protocol; pr...

[3] Discovering active tools from live gateway (JSON-RPC tools/list)...
    Discovered 5 active RAEN MCP tools:
    - raen_law_lookup           : Look up US consumer-protection law citations (FCRA, FDCPA, TILA, state...
    - raen_ticker_analysis      : Request a synthetic ticker market-consensus demo (TradingAgents payloa...
    - raen_dispute_letter       : Generate an FCRA-compliant credit dispute letter plus an SVG certifica...
    - raen_image_generate       : Generate an AI image from a text prompt (Gemini upstream). Returns bas...
    - raen_contract_analysis    : Analyze contract text for risky, one-sided, or unusual clauses. Return...

[4] Executing ElizaOS TOOL_FINDER Action...
    [ElizaOS Callback Output]:
### Available RAEN MCP Gateway Tools

| Tool Name | Title | Description | Schema Required |
|---|---|---|---|
| `raen_law_lookup` | **RAEN Law Lookup (FCRA/FDCPA/TILA/UDAP)** | Look up US consumer-protection law citations (FCRA, FDCPA, TILA, state UDAP) on a topic. Returns formal citations, plain-English summaries, reporting timelines, and statutes of limitations. Information only, not legal advice. $0.05 USDC (x402, Base). | `topic` |

[5] Executing ElizaOS LAW_LOOKUP Action for topic: "debt collection calls at work under FDCPA"...
    [ElizaOS Callback Action]: LAW_LOOKUP_ERROR
    [ElizaOS Callback Text]:
x402 Payment Required: $0.05 USDC needed to execute law lookup on Base mainnet. Set RAEN_API_KEY with a valid dev key.

==================================================================
  DEMO COMPLETE: All protocol communications verified live.
==================================================================
```
