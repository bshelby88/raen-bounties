# Explicit-opt-in RAEN x402 CLI (draft contribution)

Single-file Python CLI with standard-library HTTP and one direct signer dependency, eth-account==0.14.0. The official service snapshot is included as official_agents.json. Discoveries can also be read from an explicitly provided HTTPS directory URL.

## Scope and verified limits
- Lists the actual 12-service organizer directory; this does not assert all 12 endpoints were integration-tested.
- Defaults to no outbound prompt request and no key access. --probe performs one unsigned request to the declared same-origin POST route and stops at HTTP402.
- Explicit payment opt-in supports Base USDC EIP-3009, x402 v1/v2 envelopes, recipient/asset/domain/amount checks, an exclusive intent journal and at most one signed retry. Uncertain outcomes never trigger automatic payment retries.
- 41 tests pass, including real local HTTP transport and independent recovery of signatures from ephemeral unfunded test keys. All local settlement receipts are synthetic fixtures.
- An actual unsigned royal-ruby request returned HTTP402. NO live signed request or mainnet settlement was executed. This draft does not yet fulfill the bounty's live 402 -> settle -> 200 evidence criterion.

## Reproduce from this directory
```sh
python -m pip install -r requirements.txt
python -m unittest -v test_raen_cli test_payment
python raen-cli.py list
python raen-cli.py royal-ruby "FCRA statutory overview"
```

Optional unsigned provider probe (not a payment):
```sh
python raen-cli.py royal-ruby "FCRA statutory overview" --probe --request-json '{"topic":"FCRA statutory overview"}'
```
Exit 2 means a validated payment challenge was received without payment. Other services may need their own documented JSON payload via --request-json; a universal prompt schema is not claimed.

Payment mode is disabled unless --pay, RAEN_PAYMENT_APPROVED=YES, an explicit atomic-unit cap, an independently expected recipient, a new owner-controlled journal path, and an owner-supplied RAEN_PRIVATE_KEY are all provided. Never put keys in command arguments, source, reports or journals. The program does not emit signing keys or broadcastable authorizations. Never use a funded signer with local fixtures. The program can report a provider receipt but does not claim independent on-chain verification.

Protocol reference: coinbase/x402 exact EVM EIP-3009 client, source tree recorded in the preparation evidence. Voice/report artifacts, payout addresses and personal data are not part of this contribution. This PR makes no reservation/claim on the already-assigned bounty and does not claim acceptance or a reward.
