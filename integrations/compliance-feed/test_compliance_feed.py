"""Unit tests for RAEN Compliance Feed verification, canonical JSON, and trust scoring."""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).parent))

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
    load_pem_public_key,
)

import raen_compliance_feed as feed

# Official live public key published at https://settlement-collector.fly.dev/certify/.well-known/pubkey.pem
OFFICIAL_PUBKEY_PEM = (
    "-----BEGIN PUBLIC KEY-----\n"
    "MCowBQYDK2VwAyEAEUJm+3WydEojhg/mqa+rlYnk9hDYgoJQGyoF507O59E=\n"
    "-----END PUBLIC KEY-----\n"
)


class TestComplianceFeed(unittest.TestCase):
    def setUp(self):
        # Generate an ephemeral test Ed25519 keypair for reproducible local testing
        self.priv_key = Ed25519PrivateKey.generate()
        self.pub_key = self.priv_key.public_key()
        self.pub_key_pem = self.pub_key.public_bytes(
            Encoding.PEM,
            PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")

        self.sample_payload = {
            "certificate": "raen-compliance-feed/v1",
            "service": "royal-ruby",
            "issuer": "settlement-collector (RAEN fleet settlement telemetry)",
            "issued_at": "2026-11-17T03:00:00.000Z",
            "verdict": "live",
            "health": {
                "checked": True,
                "healthy": True,
                "http_status": 200,
                "latency_ms": 118,
            },
            "manifest": {
                "url": "https://royal-ruby.fly.dev/.well-known/x402.json",
                "fetched": True,
                "sha256": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
            },
            "quote": {
                "advertised_price_usd": 0.05,
                "network": "eip155:8453",
                "payTo": "0x9b8a27e03CEbA490953cDa8AB1291c0E13bAf72f",
                "valid": True,
            },
            "settlement_evidence": {
                "tx": "0xe650ceb639300d1ec46cf40a8c46aa9ce0393e8a60ec8aac3d4863ef7029905b",
                "payer": "0xfBC0000000000000000000000000000000002240",
                "amount_usd": 0.05,
                "settled_at": "2026-11-16T12:00:00.000Z",
                "tx_verified": True,
            },
            "delivery_evidence": {
                "settled_tx_count": 48,
                "delivered_200_count": 48,
            },
        }

    def sign_test_certificate(self, payload: dict) -> dict:
        canonical = feed.canonical_json(payload).encode("utf-8")
        sig = self.priv_key.sign(canonical)
        sig_b64 = base64.b64encode(sig).decode("utf-8")
        return {
            **payload,
            "signature": sig_b64,
            "signing_key_id": "test-key-id",
            "verify": "/certify/.well-known/pubkey.pem",
        }

    def test_canonical_json_reproducibility(self):
        """Ensure canonical_json outputs sorted keys and compact separators."""
        test_dict = {
            "z": 1,
            "a": 2,
            "m": {"nested_b": True, "nested_a": [3, 2, 1]},
        }
        res = feed.canonical_json(test_dict)
        expected = '{"a":2,"m":{"nested_a":[3,2,1],"nested_b":true},"z":1}'
        self.assertEqual(res, expected)

    def test_valid_certificate_signature_verification(self):
        """Sign and verify a clean certificate with generated test key."""
        cert = self.sign_test_certificate(self.sample_payload)
        verified = feed.verify_certificate_signature(cert, self.pub_key_pem)
        self.assertTrue(verified)

    def test_tamper_detection_in_verdict(self):
        """Modifying the verdict must invalidate the signature."""
        cert = self.sign_test_certificate(self.sample_payload)
        cert["verdict"] = "degraded"  # Tamper with signed field

        with self.assertRaises(InvalidSignature):
            feed.verify_certificate_signature(cert, self.pub_key_pem)

    def test_tamper_detection_in_nested_health(self):
        """Modifying nested health fields must invalidate the signature."""
        cert = self.sign_test_certificate(self.sample_payload)
        cert["health"]["latency_ms"] = 999  # Tamper with nested data

        with self.assertRaises(InvalidSignature):
            feed.verify_certificate_signature(cert, self.pub_key_pem)

    def test_envelope_metadata_does_not_affect_payload(self):
        """Envelope fields like signing_key_id or verify are not signed."""
        cert = self.sign_test_certificate(self.sample_payload)
        cert["signing_key_id"] = "different-key-id"
        cert["verify"] = "/different/path.pem"

        # Verification still passes because envelope fields are excluded from canonical digest
        self.assertTrue(feed.verify_certificate_signature(cert, self.pub_key_pem))

    def test_missing_or_corrupt_signature(self):
        """Missing or corrupt signatures raise ValueError."""
        cert = self.sign_test_certificate(self.sample_payload)
        cert["signature"] = "not-valid-base64-!@#$"

        with self.assertRaises(ValueError):
            feed.verify_certificate_signature(cert, self.pub_key_pem)

        del cert["signature"]
        with self.assertRaises(ValueError):
            feed.verify_certificate_signature(cert, self.pub_key_pem)

    def test_official_public_key_loading(self):
        """Verify official production Ed25519 public key parses successfully."""
        pub = load_pem_public_key(OFFICIAL_PUBKEY_PEM.encode("utf-8"))
        self.assertIsNotNone(pub)

    def test_evaluate_trust_score_grade_a(self):
        """Live, healthy, verified service scores Grade A (>=85)."""
        cert = self.sign_test_certificate(self.sample_payload)
        report = feed.evaluate_trust_score(cert, self.pub_key_pem)

        self.assertEqual(report.grade, "A")
        self.assertGreaterEqual(report.trust_score, 85)
        self.assertTrue(report.signature_valid)
        self.assertTrue(report.healthy)
        self.assertEqual(report.verdict, "live")

    def test_evaluate_trust_score_tampered_fails(self):
        """Tampered certificate gets trust score 0 and Grade F."""
        cert = self.sign_test_certificate(self.sample_payload)
        cert["verdict"] = "degraded"  # Tamper

        report = feed.evaluate_trust_score(cert, self.pub_key_pem)
        self.assertEqual(report.grade, "F")
        self.assertEqual(report.trust_score, 0)
        self.assertFalse(report.signature_valid)
        self.assertEqual(report.verdict, "untrusted")


if __name__ == "__main__":
    unittest.main()
