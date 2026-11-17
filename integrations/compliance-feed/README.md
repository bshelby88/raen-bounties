# RAEN Compliance Feed — Crawler & Indexer Integration

Production Python client, offline Ed25519 signature verifier, and crawler trust scoring library for the **RAEN Compliance Feed** (Issue #21).

RAEN sells machine-readable, cryptographically signed compliance certificates for the 12-service fleet on Base mainnet (`GET https://settlement-collector.fly.dev/certify/{service}`, $0.01 via x402). Every certificate is signed with Ed25519 over deterministic canonical JSON, backed by live probe outcomes (manifest SHA-256, live 402 quote validity, latency, on-chain settlement proof, and open claims count).

---

## Features

- **Offline Ed25519 Signature Verification**: Cryptographically verifies certificate authenticity against the official published public key (`GET /certify/.well-known/pubkey.pem`) without network calls.
- **Canonical JSON Engine**: Matches `certify.js` `canonicalJson` byte-for-byte with sorted object keys and compact separators.
- **Tamper Detection**: Any modification to payload fields (verdict, latency, manifest hash, tx hash) immediately triggers signature invalidation (`InvalidSignature`).
- **Crawler Trust Scoring (`evaluate_trust_score`)**: Computes an objective 0–100 reliability score (Grade A/B/C/F) factoring verdict, latency, manifest health, and on-chain settlement proof for crawler ranking and search indexing.
- **CLI & Module Interface**: Usable as a command-line tool or as a zero-fuss Python module.

---

## Quickstart

### Installation

```bash
pip install -r requirements.txt
```

### CLI Usage

```bash
# 1. Fetch live feed discovery metadata & Ed25519 public key
python raen_compliance_feed.py info

# 2. Verify certificate signature offline
python raen_compliance_feed.py verify certificate.json

# 3. Calculate crawler trust score & reliability report
python raen_compliance_feed.py score certificate.json
```

---

## Python Integration for Crawlers / Indexers

Integrate directly into your indexing pipeline, crawler middleware, or trust-score aggregator:

```python
from raen_compliance_feed import ComplianceFeedClient, evaluate_trust_score, verify_certificate_signature

client = ComplianceFeedClient()

# Fetch official public key once and cache it
pubkey_pem = client.get_public_key_pem()

# In your crawler loop:
certificate = ... # Fetched via x402 or historical snapshot

# 1. Cryptographically verify certificate authenticity offline
is_authentic = verify_certificate_signature(certificate, pubkey_pem)

# 2. Compute crawler trust score & ranking metrics
report = evaluate_trust_score(certificate, pubkey_pem)
print(f"Service:     {report.service}")
print(f"Trust Score: {report.trust_score}/100 (Grade: {report.grade})")
print(f"Verdict:     {report.verdict}")
print(f"Latency:     {report.latency_ms} ms")
print(f"On-chain tx: {report.tx_verified}")
```

---

## Running Unit Tests

```bash
python -m unittest test_compliance_feed.py
```

The test suite covers:
- Deterministic canonical JSON key sorting and nested array formatting.
- Ed25519 signing and verification with ephemeral test keys.
- Field-level tamper detection (verdict alteration, nested health tampering).
- Envelope metadata exclusion (`signature`, `signing_key_id`, `verify`).
- Public key compatibility with official production PEM (`MCowBQYDK2VwAyEAEUJm...`).
- Trust score computation (Grade A for live verified services, Grade F / score 0 for tampered certificates).

---

## Protocol Reference

- **Public Key**: `https://settlement-collector.fly.dev/certify/.well-known/pubkey.pem`
- **Discovery Endpoint**: `https://settlement-collector.fly.dev/certify`
- **Signing Algorithm**: Ed25519 over UTF-8 canonical JSON
- **Facilitator**: x402 exact USDC micropayments on Base mainnet (`eip155:8453`)
