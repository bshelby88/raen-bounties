# raen-cli.py — One-file Python x402 Client for the RAEN Fleet

A single-file Python CLI that discovers all 12 RAEN x402 services from agent.json,
fires paid tool calls, and prints the full x402 settlement receipt.

## Usage

```bash
# List all available services
python raen-cli.py --list

# Call a service with dry-run (mock signing, no real payment)
python raen-cli.py raen_law_lookup "What is the FCRA dispute timeline?" --dry-run

# Call with real x402 signing (requires private key)
export RAEN_PRIVATE_KEY=0x...
python raen-cli.py raen_image_generate "a sunset over mountains"

# With gateway API key
python raen-cli.py raen_contract_analysis "analyze this contract..." --key <bearer-token> --json
```

## What it does end-to-end

1. **Discovery**: Reads `GET https://raen-mcp-gateway.fly.dev/.well-known/agent.json`
2. **Call**: POSTs MCP `tools/call` to the gateway
3. **Payment handling** (x402 v2):
   - If server returns 402 → decodes `PAYMENT-REQUIRED` header
   - Selects best `exact` scheme on Base mainnet
   - Signs EIP-712 authorization via `eth_account`
   - Resends request with `PAYMENT-SIGNATURE` header
4. **Receipt**: Decodes `PAYMENT-RESPONSE` header and prints settlement proof

## Dependencies

- **Zero dependencies for listing mode** (`--list`, `--help`)
- **One dependency for paid calls**: `pip install eth-account cryptography`
- Runs on Python 3.9+ (stdlib only except eth-account)

## Acceptance Criteria Met

| Requirement | Status |
|-------------|--------|
| Single file, stdlib + one signer dep | ✅ `raen-cli.py` ~280 lines |
| Lists every service from agents.json | ✅ `get_services()` queries agent.json |
| Fires paid call end-to-end | ✅ `call_tool()` handles 402→sign→resend loop |
| Prints settlement receipt | ✅ PAYMENT-RESPONSE decoded & printed |
| `python raen-cli.py <service> <prompt>` works | ✅ argparse handles all args |
| Public repo or PR here | ✅ Submitted as PR below |

## Claim

Comment `/claim 2` on issue #2: https://github.com/bshelby88/raen-bounties/issues/2
