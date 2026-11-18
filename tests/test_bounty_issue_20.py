import json
import time
import hashlib
import secrets
import unittest
from dataclasses import dataclass, field
from typing import Optional, Dict, List
from unittest.mock import Mock, patch


@dataclass
class Settlement:
    id: str
    amount: int
    recipient: str
    nonce: int
    timestamp: int = field(default_factory=lambda: int(time.time()))


@dataclass
class ClaimCode:
    code: str
    settlement_id: str
    amount: int
    recipient: str
    created_at: int
    redeemed_at: Optional[int] = None
    is_redeemed: bool = False


class ClaimCodeGenerator:
    PREFIX = "RAEN-"
    HEX_LENGTH = 12

    @classmethod
    def generate(cls, settlement: Settlement) -> ClaimCode:
        hex_part = secrets.token_hex(cls.HEX_LENGTH // 2).upper()
        code = f"{cls.PREFIX}{hex_part}"
        return ClaimCode(
            code=code,
            settlement_id=settlement.id,
            amount=settlement.amount,
            recipient=settlement.recipient,
            created_at=int(time.time())
        )

    @classmethod
    def validate_format(cls, code: str) -> bool:
        if not code.startswith(cls.PREFIX):
            return False
        hex_part = code[len(cls.PREFIX):]
        if len(hex_part) != cls.HEX_LENGTH:
            return False
        try:
            int(hex_part, 16)
            return True
        except ValueError:
            return False


class MockChainClient:
    def __init__(self):
        self.settlements: Dict[str, Settlement] = {}
        self.unfinalized_ids: set = set()

    def get_settlement(self, settlement_id: str) -> Optional[Settlement]:
        return self.settlements.get(settlement_id)

    def verify_settlement_finalized(self, settlement_id: str) -> bool:
        if settlement_id in self.unfinalized_ids:
            return False
        return settlement_id in self.settlements


class MockHTTPClient:
    def __init__(self):
        self.responses: Dict[str, Dict] = {}

    def post(self, url: str, json_data: Dict) -> Mock:
        resp = Mock()
        resp.status_code = 200
        resp.json.return_value = self.responses.get(url, {"success": True})
        return resp


class ClaimService:
    def __init__(self, chain_client: MockChainClient, http_client: MockHTTPClient):
        self.chain = chain_client
        self.http = http_client
        self.claims: Dict[str, ClaimCode] = {}

    def issue_claim(self, settlement_id: str) -> ClaimCode:
        settlement = self.chain.get_settlement(settlement_id)
        if not settlement:
            raise ValueError(f"Settlement {settlement_id} not found")
        if not self.chain.verify_settlement_finalized(settlement_id):
            raise ValueError(f"Settlement {settlement_id} not finalized")

        claim = ClaimCodeGenerator.generate(settlement)
        self.claims[claim.code] = claim
        return claim

    def redeem_claim(self, code: str, recipient: str) -> ClaimCode:
        if not ClaimCodeGenerator.validate_format(code):
            raise ValueError("Invalid claim code format")

        claim = self.claims.get(code)
        if not claim:
            raise ValueError("Claim code not found")

        if claim.is_redeemed:
            raise ValueError("Claim already redeemed")

        if claim.recipient.lower() != recipient.lower():
            raise ValueError("Recipient mismatch")

        claim.is_redeemed = True
        claim.redeemed_at = int(time.time())
        return claim

    def get_claim(self, code: str) -> Optional[ClaimCode]:
        return self.claims.get(code)


class TestClaimCodeFlow(unittest.TestCase):
    def setUp(self):
        self.chain = MockChainClient()
        self.http = MockHTTPClient()
        self.service = ClaimService(self.chain, self.http)

        self.settlement = Settlement(
            id="SETL-001",
            amount=1000000,
            recipient="0xAbCd1234",
            nonce=42
        )
        self.chain.settlements[self.settlement.id] = self.settlement

    def test_generate_claim_code_format(self):
        claim = self.service.issue_claim(self.settlement.id)
        self.assertTrue(claim.code.startswith("RAEN-"))
        self.assertEqual(len(claim.code), 5 + 12)
        hex_part = claim.code[5:]
        self.assertTrue(all(c in "0123456789ABCDEF" for c in hex_part))

    def test_claim_code_uniqueness(self):
        codes = set()
        for _ in range(100):
            claim = self.service.issue_claim(self.settlement.id)
            self.assertNotIn(claim.code, codes)
            codes.add(claim.code)

    def test_validate_format_valid(self):
        self.assertTrue(ClaimCodeGenerator.validate_format("RAEN-8922B9225B00"))
        self.assertTrue(ClaimCodeGenerator.validate_format("RAEN-ABCDEF123456"))
        self.assertTrue(ClaimCodeGenerator.validate_format("RAEN-000000000000"))
        self.assertTrue(ClaimCodeGenerator.validate_format("RAEN-FFFFFFFFFFFF"))

    def test_validate_format_invalid_prefix(self):
        self.assertFalse(ClaimCodeGenerator.validate_format("RAENX-8922B9225B"))
        self.assertFalse(ClaimCodeGenerator.validate_format("RAEN_8922B9225B"))
        self.assertFalse(ClaimCodeGenerator.validate_format("WRONG-8922B9225B"))

    def test_validate_format_invalid_length(self):
        self.assertFalse(ClaimCodeGenerator.validate_format("RAEN-8922B9225"))  # 11 chars
        self.assertFalse(ClaimCodeGenerator.validate_format("RAEN-8922B9225B1"))  # 13 chars
        self.assertFalse(ClaimCodeGenerator.validate_format("RAEN-"))  # 0 chars

    def test_validate_format_invalid_hex(self):
        self.assertFalse(ClaimCodeGenerator.validate_format("RAEN-GGGGGGGGGGGG"))
        self.assertFalse(ClaimCodeGenerator.validate_format("RAEN-8922B9225BZ"))
        self.assertFalse(ClaimCodeGenerator.validate_format("RAEN-8922B9225B!"))

    def test_issue_claim_missing_settlement(self):
        with self.assertRaises(ValueError) as ctx:
            self.service.issue_claim("NONEXISTENT")
        self.assertIn("not found", str(ctx.exception))

    def test_issue_claim_unfinalized(self):
        self.chain.unfinalized_ids.add(self.settlement.id)
        with self.assertRaises(ValueError) as ctx:
            self.service.issue_claim(self.settlement.id)
        self.assertIn("not finalized", str(ctx.exception))

    def test_redeem_valid_claim(self):
        claim = self.service.issue_claim(self.settlement.id)
        redeemed = self.service.redeem_claim(claim.code, self.settlement.recipient)
        self.assertTrue(redeemed.is_redeemed)
        self.assertIsNotNone(redeemed.redeemed_at)
        self.assertEqual(redeemed.code, claim.code)

    def test_redeem_invalid_format(self):
        with self.assertRaises(ValueError) as ctx:
            self.service.redeem_claim("INVALID-CODE", self.settlement.recipient)
        self.assertIn("Invalid claim code format", str(ctx.exception))

    def test_redeem_nonexistent_code(self):
        with self.assertRaises(ValueError) as ctx:
            self.service.redeem_claim("RAEN-000000000000", self.settlement.recipient)
        self.assertIn("not found", str(ctx.exception))

    def test_redeem_already_redeemed(self):
        claim = self.service.issue_claim(self.settlement.id)
        self.service.redeem_claim(claim.code, self.settlement.recipient)
        with self.assertRaises(ValueError) as ctx:
            self.service.redeem_claim(claim.code, self.settlement.recipient)
        self.assertIn("already redeemed", str(ctx.exception))

    def test_redeem_wrong_recipient(self):
        claim = self.service.issue_claim(self.settlement.id)
        with self.assertRaises(ValueError) as ctx:
            self.service.redeem_claim(claim.code, "0xDifferentRecipient")
        self.assertIn("Recipient mismatch", str(ctx.exception))

    def test_redeem_case_insensitive_recipient(self):
        claim = self.service.issue_claim(self.settlement.id)
        redeemed = self.service.redeem_claim(claim.code, self.settlement.recipient.upper())
        self.assertTrue(redeemed.is_redeemed)

    def test_claim_data_integrity(self):
        claim = self.service.issue_claim(self.settlement.id)
        self.assertEqual(claim.settlement_id, self.settlement.id)
        self.assertEqual(claim.amount, self.settlement.amount)
        self.assertEqual(claim.recipient, self.settlement.recipient)
        self.assertFalse(claim.is_redeemed)
        self.assertIsNone(claim.redeemed_at)

    def test_get_claim(self):
        claim = self.service.issue_claim(self.settlement.id)
        retrieved = self.service.get_claim(claim.code)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.code, claim.code)

    def test_get_nonexistent_claim(self):
        result = self.service.get_claim("RAEN-000000000000")
        self.assertIsNone(result)


def test_sample():
    suite = unittest.TestLoader().loadTestsFromTestCase(TestClaimCodeFlow)
    runner = unittest.TextTestRunner(verbosity=0, stream=open('/dev/null', 'w'))
    result = runner.run(suite)
    assert result.wasSuccessful(), f"Failures: {len(result.failures)}, Errors: {len(result.errors)}"
    print("Self-test passed")


if __name__ == '__main__':
    test_sample()