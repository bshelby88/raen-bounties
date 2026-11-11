# BOUNTY-02: One-file Python CLI client for the 12-service x402 fleet

## Summary
- **`raen-cli.py`**: Single-file Python CLI client supporting all 12 RAEN x402 services on Base Mainnet (`chainId = 8453`, USDC `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`).
- **Service Discovery (`--list`)**: Loads `agents.json` from a local file, URL, or the built-in 12-service fleet catalog.
- **Full HTTP 402 -> EIP-3009 `TransferWithAuthorization` -> `X-PAYMENT` Settlement Loop**: Automatically parses HTTP `402 Payment Required` challenges, signs the EIP-712 / EIP-3009 authorization payload, retries with `X-PAYMENT`, and prints the response alongside the decoded `X-PAYMENT-RESPONSE` receipt.
- **Zero-Capital Loopback Verification (`--simulate`)**: Spins up an ephemeral local x402 HTTP server returning `402 Payment Required` on unauthenticated requests and `200 OK` + settlement receipt once a valid `X-PAYMENT` header is supplied.

## Usage
```bash
python raen-cli.py --list
python raen-cli.py signal-scanner "Scan top Base momentum tokens" --simulate
```
