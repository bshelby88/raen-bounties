#!/usr/bin/env python3
"""RAEN Compliance Feed Client & Offline Ed25519 Verifier.

Provides offline cryptographic verification and crawler/indexer integration for the
RAEN Compliance Feed (signed machine-readable compliance certificates).

Endpoints:
  GET https://settlement-collector.fly.dev/certify
  GET https://settlement-collector.fly.dev/certify/.well-known/pubkey.pem
  GET https://settlement-collector.fly.dev/certify/{service}
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Tuple

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key

DEFAULT_COLLECTOR_URL = "https://settlement-collector.fly.dev"
DEFAULT_USER_AGENT = "raen-compliance-feed-client/1.0"

# Envelope metadata keys omitted from the signed payload
ENVELOPE_KEYS = {"signature", "signing_key_id", "verify"}


def canonical_json(value: Any) -> str:
    """Stable JSON stringifier with sorted object keys matching certify.js canonicalJson.

    Ensures cryptographic signature verification is strictly reproducible across runtimes.
    """
    if isinstance(value, list):
        return "[" + ",".join(canonical_json(v) for v in value) + "]"
    if isinstance(value, dict):
        items = []
        for k in sorted(value.keys()):
            items.append(json.dumps(k) + ":" + canonical_json(value[k]))
        return "{" + ",".join(items) + "}"
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def extract_payload(certificate: Dict[str, Any]) -> Dict[str, Any]:
    """Extract raw signed certificate payload excluding envelope wrapper fields."""
    return {k: v for k, v in certificate.items() if k not in ENVELOPE_KEYS}


def verify_certificate_signature(
    certificate: Dict[str, Any],
    public_key_pem: str | bytes,
) -> bool:
    """Verify an Ed25519 signature over a signed RAEN compliance certificate.

    Args:
        certificate: Decoded certificate dictionary containing a 'signature' field.
        public_key_pem: PEM-encoded Ed25519 public key.

    Returns:
        True if the signature is cryptographically valid against the public key.

    Raises:
        ValueError: If certificate is missing 'signature' or malformed.
        InvalidSignature: If the signature does not match the payload.
    """
    if not isinstance(certificate, dict):
        raise ValueError("certificate must be a dictionary")

    sig_b64 = certificate.get("signature")
    if not sig_b64 or not isinstance(sig_b64, str):
        raise ValueError("certificate missing or invalid 'signature' string")

    try:
        signature_bytes = base64.b64decode(sig_b64, validate=True)
    except Exception as e:
        raise ValueError(f"invalid base64 signature encoding: {e}") from e

    pem_bytes = public_key_pem.encode("utf-8") if isinstance(public_key_pem, str) else public_key_pem
    try:
        pub_key = load_pem_public_key(pem_bytes)
    except Exception as e:
        raise ValueError(f"invalid PEM public key: {e}") from e

    if not isinstance(pub_key, Ed25519PublicKey):
        raise ValueError("public key must be an Ed25519 key")

    payload = extract_payload(certificate)
    canonical_bytes = canonical_json(payload).encode("utf-8")

    pub_key.verify(signature_bytes, canonical_bytes)
    return True


@dataclass(frozen=True)
class TrustReport:
    service: str
    verdict: str  # 'live', 'degraded', 'down', or 'untrusted'
    trust_score: int  # 0 to 100
    grade: str  # 'A', 'B', 'C', 'F'
    signature_valid: bool
    healthy: bool
    latency_ms: Optional[int]
    manifest_sha256: Optional[str]
    tx_verified: bool
    details: Dict[str, Any]


def evaluate_trust_score(
    certificate: Dict[str, Any],
    public_key_pem: Optional[str | bytes] = None,
) -> TrustReport:
    """Calculate an objective trust and reliability score (0-100) for a fleet service.

    Scoring rubrics:
      - Valid Ed25519 cryptographic signature: required (failure results in score 0 / untrusted)
      - Verdict: live (+35 pts), degraded (+15 pts), down (0 pts)
      - Live health check status: healthy (+20 pts)
      - Network latency: <250ms (+15 pts), <600ms (+10 pts), <1500ms (+5 pts)
      - Manifest & Quote validity: fetched (+10 pts), quote valid (+10 pts)
      - On-chain tx settlement evidence: tx_verified (+10 pts)
    """
    svc = str(certificate.get("service") or "unknown")

    # Cryptographic integrity check
    sig_valid = False
    if public_key_pem:
        try:
            sig_valid = verify_certificate_signature(certificate, public_key_pem)
        except (InvalidSignature, ValueError):
            sig_valid = False
    else:
        sig_valid = True  # Key omitted; skip signature enforcement

    if not sig_valid:
        return TrustReport(
            service=svc,
            verdict="untrusted",
            trust_score=0,
            grade="F",
            signature_valid=False,
            healthy=False,
            latency_ms=None,
            manifest_sha256=None,
            tx_verified=False,
            details={"error": "Signature verification failed or payload tampered"},
        )

    score = 0
    verdict = str(certificate.get("verdict", "down"))
    if verdict == "live":
        score += 35
    elif verdict == "degraded":
        score += 15

    health = certificate.get("health", {})
    healthy = bool(health.get("healthy"))
    if healthy:
        score += 20

    latency = health.get("latency_ms")
    if latency is not None and isinstance(latency, (int, float)):
        if latency < 250:
            score += 15
        elif latency < 600:
            score += 10
        elif latency < 1500:
            score += 5

    manifest = certificate.get("manifest", {})
    if manifest.get("fetched"):
        score += 10

    quote = certificate.get("quote", {})
    if quote.get("valid"):
        score += 10

    settle = certificate.get("settlement_evidence", {})
    tx_verified = bool(settle.get("tx_verified"))
    if tx_verified:
        score += 10

    score = min(100, max(0, score))
    if score >= 85:
        grade = "A"
    elif score >= 70:
        grade = "B"
    elif score >= 50:
        grade = "C"
    else:
        grade = "F"

    return TrustReport(
        service=svc,
        verdict=verdict,
        trust_score=score,
        grade=grade,
        signature_valid=sig_valid,
        healthy=healthy,
        latency_ms=latency,
        manifest_sha256=manifest.get("sha256"),
        tx_verified=tx_verified,
        details={
            "issued_at": certificate.get("issued_at"),
            "issuer": certificate.get("issuer"),
            "claims": certificate.get("claims", {}),
            "settlement_evidence": settle,
        },
    )


class ComplianceFeedClient:
    """Client for discovering, polling, and cryptographically verifying the RAEN Compliance Feed."""

    def __init__(
        self,
        base_url: str = DEFAULT_COLLECTOR_URL,
        user_agent: str = DEFAULT_USER_AGENT,
        timeout: int = 15,
    ):
        self.base_url = base_url.rstrip("/")
        self.user_agent = user_agent
        self.timeout = timeout
        self._cached_pubkey_pem: Optional[str] = None

    def _get(self, path: str) -> Tuple[int, Dict[str, str], bytes]:
        url = f"{self.base_url}{path}" if path.startswith("/") else f"{self.base_url}/{path}"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/json, text/plain",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.status, dict(resp.headers), resp.read()
        except urllib.error.HTTPError as err:
            return err.code, dict(err.headers), err.read()

    def get_public_key_pem(self, refresh: bool = False) -> str:
        """Fetch and cache the official Ed25519 verification public key."""
        if self._cached_pubkey_pem and not refresh:
            return self._cached_pubkey_pem

        status, _, body = self._get("/certify/.well-known/pubkey.pem")
        if status != 200:
            raise RuntimeError(f"failed to fetch public key: HTTP {status}")

        pem = body.decode("utf-8").strip()
        self._cached_pubkey_pem = pem
        return pem

    def get_feed_info(self) -> Dict[str, Any]:
        """Fetch free product discovery information and supported services catalog."""
        status, _, body = self._get("/certify")
        if status != 200:
            raise RuntimeError(f"failed to fetch feed info: HTTP {status}")
        return json.loads(body.decode("utf-8"))

    def verify(self, certificate: Dict[str, Any]) -> bool:
        """Verify certificate signature against the official cached public key."""
        pubkey = self.get_public_key_pem()
        return verify_certificate_signature(certificate, pubkey)

    def evaluate(self, certificate: Dict[str, Any]) -> TrustReport:
        """Verify certificate and calculate an indexer trust score."""
        pubkey = self.get_public_key_pem()
        return evaluate_trust_score(certificate, pubkey)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="raen-compliance",
        description="RAEN Compliance Feed — Ed25519 offline certificate verification & trust scoring",
    )
    sub = ap.add_subparsers(dest="command", required=True)

    # Subcommand: info
    sub.add_parser("info", help="Fetch feed metadata and public key from endpoint")

    # Subcommand: verify
    p_verify = sub.add_parser("verify", help="Verify signature of a certificate JSON file")
    p_verify.add_argument("file", help="Path to certificate JSON file")
    p_verify.add_argument("--key", help="Optional path to custom public key PEM file")

    # Subcommand: score
    p_score = sub.add_parser("score", help="Verify and compute crawler trust score for a certificate file")
    p_score.add_argument("file", help="Path to certificate JSON file")
    p_score.add_argument("--key", help="Optional path to custom public key PEM file")

    args = ap.parse_args(argv)
    client = ComplianceFeedClient()

    if args.command == "info":
        try:
            info = client.get_feed_info()
            pubkey = client.get_public_key_pem()
            print("==================================================================")
            print("  RAEN Compliance Feed Discovery")
            print("==================================================================")
            print(f"Product:       {info.get('product')}")
            print(f"Version:       {info.get('version')}")
            print(f"Base price:    {info.get('price')} USDC (exact scheme on Base)")
            print(f"Services:      {len(info.get('services', []))} available services")
            print("\nOfficial Ed25519 Public Key:")
            print(pubkey)
            return 0
        except Exception as e:
            print(f"Error fetching feed info: {e}", file=sys.stderr)
            return 1

    if args.command in ("verify", "score"):
        try:
            with open(args.file, "r", encoding="utf-8") as f:
                cert = json.load(f)
        except Exception as e:
            print(f"Error reading certificate file: {e}", file=sys.stderr)
            return 1

        if args.key:
            with open(args.key, "r", encoding="utf-8") as f:
                pubkey = f.read()
        else:
            pubkey = client.get_public_key_pem()

        try:
            valid = verify_certificate_signature(cert, pubkey)
        except InvalidSignature:
            print("\x1b[31m✗ Signature verification FAILED: signature mismatch / payload tampered\x1b[0m", file=sys.stderr)
            return 2
        except Exception as e:
            print(f"\x1b[31m✗ Verification error: {e}\x1b[0m", file=sys.stderr)
            return 2

        if args.command == "verify":
            print(f"\x1b[32m✓ Signature Verified: valid Ed25519 certificate for '{cert.get('service')}'\x1b[0m")
            print(f"  Issuer:    {cert.get('issuer')}")
            print(f"  Issued at: {cert.get('issued_at')}")
            print(f"  Verdict:   {cert.get('verdict')}")
            return 0

        if args.command == "score":
            report = evaluate_trust_score(cert, pubkey)
            print("==================================================================")
            print(f"  Compliance Trust Report: {report.service}")
            print("==================================================================")
            print(f"  Trust Score:   {report.trust_score}/100 (Grade: {report.grade})")
            print(f"  Verdict:       {report.verdict}")
            print(f"  Signature:     {'VERIFIED' if report.signature_valid else 'INVALID'}")
            print(f"  Health:        {'HEALTHY' if report.healthy else 'UNHEALTHY'} ({report.latency_ms} ms)")
            print(f"  On-chain tx:   {'VERIFIED' if report.tx_verified else 'NO TX'}")
            print(f"  Manifest SHA:  {report.manifest_sha256}")
            return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
