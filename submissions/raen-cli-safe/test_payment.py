"""Signing/transport tests use ephemeral unfunded keys and explicit synthetic receipts only."""
import base64
import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from eth_account import Account
from eth_account.messages import encode_typed_data
from test_raen_cli import cli, directory, PAYEE

SYNTHETIC_TX_HASH = "0x" + "ab" * 32


def full_challenge(version=2):
    req = {"scheme": "exact", "network": "eip155:8453", "amount": "50000", "payTo": PAYEE,
           "asset": cli.USDC_BASE, "maxTimeoutSeconds": 120,
           "extra": {"name": "USD Coin", "version": "2"}}
    if version == 1:
        req["network"] = "base"; req["maxAmountRequired"] = req.pop("amount")
    return {"x402Version": version, "accepts": [req]}


def fake_receipt(payer):
    value = {"success": True, "network": "eip155:8453", "transaction": SYNTHETIC_TX_HASH, "payer": payer}
    return {"PAYMENT-RESPONSE": base64.b64encode(json.dumps(value).encode()).decode()}


class SigningTests(unittest.TestCase):
    def setUp(self): self.account = Account.create()

    def prepare(self, obj=None, **kwargs):
        return cli.prepare_payment_header(obj or full_challenge(), PAYEE, kwargs.pop("cap", "50000"), self.account.key, **kwargs)

    def test_v2_signature_recovered_independently(self):
        prepared = self.prepare(now=1700000000)
        envelope = json.loads(base64.b64decode(prepared["value"]))
        auth = envelope["payload"]["authorization"]
        self.assertEqual(prepared["header_name"], "PAYMENT-SIGNATURE")
        self.assertEqual(envelope["accepted"]["asset"], cli.USDC_BASE)
        self.assertEqual(auth["to"], PAYEE)
        self.assertEqual(auth["value"], "50000")
        self.assertEqual(auth["validAfter"], "0")
        self.assertEqual(auth["validBefore"], "1700000120")
        recovered = Account.recover_message(encode_typed_data(full_message=cli.typed_authorization(auth)), signature=envelope["payload"]["signature"])
        self.assertEqual(recovered, self.account.address)

    def test_v1_wire_format_and_recovery(self):
        prepared = self.prepare(full_challenge(1), now=1700000000)
        envelope = json.loads(base64.b64decode(prepared["value"]))
        self.assertEqual(prepared["header_name"], "X-PAYMENT")
        self.assertEqual(envelope["network"], "base")
        self.assertEqual(envelope["payload"]["authorization"]["validAfter"], "1699999400")
        auth = envelope["payload"]["authorization"]
        recovered = Account.recover_message(encode_typed_data(full_message=cli.typed_authorization(auth)), signature=envelope["payload"]["signature"])
        self.assertEqual(recovered, self.account.address)

    def test_nonce_is_unique(self):
        a = json.loads(base64.b64decode(self.prepare()["value"]))
        b = json.loads(base64.b64decode(self.prepare()["value"]))
        self.assertNotEqual(a["payload"]["authorization"]["nonce"], b["payload"]["authorization"]["nonce"])

    def test_budget_cap_rejects_before_signing(self):
        with self.assertRaises(ValueError): self.prepare(cap="49999")

    def test_invalid_budget_not_coerced(self):
        for cap in [50000, True, "-1", "050000"]:
            with self.assertRaises(ValueError): self.prepare(cap=cap)

    def test_wrong_asset_rejected(self):
        c = full_challenge(); c["accepts"][0]["asset"] = "0x" + "2" * 40
        with self.assertRaises(ValueError): self.prepare(c)

    def test_wrong_domain_rejected(self):
        c = full_challenge(); c["accepts"][0]["extra"]["name"] = "Other Token"
        with self.assertRaises(ValueError): self.prepare(c)

    def test_permit2_not_silently_substituted(self):
        c = full_challenge(); c["accepts"][0]["extra"]["assetTransferMethod"] = "permit2"
        with self.assertRaises(ValueError): self.prepare(c)

    def test_timeout_and_boolean_timeout_rejected(self):
        for timeout in [0, -1, True]:
            c = full_challenge(); c["accepts"][0]["maxTimeoutSeconds"] = timeout
            with self.assertRaises(ValueError): self.prepare(c)

    def test_expiry_capped(self):
        c = full_challenge(); c["accepts"][0]["maxTimeoutSeconds"] = 7200
        p = self.prepare(c, now=1700000000)
        a = json.loads(base64.b64decode(p["value"]))["payload"]["authorization"]
        self.assertEqual(a["validBefore"], "1700000600")


class RoundtripFixtureTests(unittest.TestCase):
    def setUp(self):
        self.account = Account.create(); self.tmp = tempfile.TemporaryDirectory(prefix="raen-fixture-")
        self.journal = Path(self.tmp.name) / "intent.jsonl"; self.posts = 0; self.mode = "success"

    def tearDown(self): self.tmp.cleanup()

    def transport(self, url, data=None, allow_loopback=False, payment_header=None):
        if data is None: return 200, {}, b'{"endpoints":{"/api/test":{"method":"POST"}}}'
        self.posts += 1
        if payment_header is None: return 402, {}, json.dumps(full_challenge()).encode()
        self.assertEqual(self.posts, 2)
        if self.mode == "timeout": raise TimeoutError("synthetic local test timeout")
        if self.mode == "rejected": return 402, {}, b"{}"
        if self.mode == "missing": return 200, {}, b"{}"
        return 200, fake_receipt(self.account.address), b'{"test_fixture_only":true}'

    def run_case(self, approved=True):
        with patch.object(cli, "request", side_effect=self.transport):
            return cli.run_paid(directory(), "fixture", "test-only prompt", approved=approved,
                                expected_payee=PAYEE, max_amount_atomic="50000", private_key=self.account.key,
                                journal_path=self.journal)

    def test_protocol_loop_with_synthetic_receipt(self):
        result = self.run_case()
        self.assertEqual(self.posts, 2)
        self.assertTrue(result["server_reported_settlement"])
        self.assertFalse(result["settlement_verified"])
        text = self.journal.read_text()
        self.assertTrue(self.account.key.hex() not in text, "journal must never contain a signer key")
        self.assertTrue('"signature"' not in text, "journal must never contain a broadcastable authorization")

    def test_timeout_marks_uncertain_without_retry(self):
        self.mode = "timeout"; result = self.run_case()
        self.assertEqual(result["status"], "payment_outcome_unknown_no_retry")
        self.assertTrue(result["payment_attempted"])
        self.assertFalse(result["automatic_retry"])
        self.assertEqual(self.posts, 2)

    def test_second_402_is_not_retried(self):
        self.mode = "rejected"; result = self.run_case()
        self.assertEqual(result["status"], "signed_request_rejected_no_retry")
        self.assertEqual(self.posts, 2)

    def test_missing_receipt_is_not_called_settled(self):
        self.mode = "missing"; result = self.run_case()
        self.assertFalse(result["server_reported_settlement"])
        self.assertEqual(self.posts, 2)

    def test_existing_intent_cannot_be_overwritten(self):
        self.journal.write_text("existing pending intent")
        with self.assertRaises(FileExistsError): self.run_case()
        self.assertEqual(self.posts, 1)
        self.assertEqual(self.journal.read_text(), "existing pending intent")

    def test_missing_approval_prevents_any_network_call(self):
        with self.assertRaises(ValueError): self.run_case(approved=False)
        self.assertEqual(self.posts, 0)


class CLIPaymentGateTests(unittest.TestCase):
    def call_main(self, argv, env):
        import io
        from contextlib import redirect_stdout, redirect_stderr
        with patch.object(cli.os, "environ", env), patch.object(cli, "request") as net:
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()): result = cli.main(argv)
            net.assert_not_called()
            return result

    def test_no_explicit_environment_approval_prevents_payment(self):
        class Guard(dict):
            def get(self, key, default=None):
                if key == "RAEN_PRIVATE_KEY": raise AssertionError("key must not be accessed before approval")
                return super().get(key, default)
        self.assertEqual(self.call_main(["royal-ruby", "hello", "--pay"], Guard()), 3)

    def test_probe_and_pay_cannot_be_combined(self):
        self.assertEqual(self.call_main(["royal-ruby", "hello", "--probe", "--pay"], {"RAEN_PAYMENT_APPROVED": "YES"}), 3)

    def test_missing_signer_cannot_trigger_network(self):
        self.assertEqual(self.call_main(["royal-ruby", "hello", "--pay", "--max-amount-atomic", "50000",
                                        "--expected-pay-to", PAYEE, "--journal", "unused-test-intent.jsonl"],
                                       {"RAEN_PAYMENT_APPROVED": "YES"}), 3)


class SignedHTTPHandler(BaseHTTPRequestHandler):
    account = None
    posts = 0
    signature_verified = False
    def log_message(self, format, *args): pass
    def emit(self, code, body, headers=None):
        raw = json.dumps(body).encode(); self.send_response(code)
        self.send_header("Content-Type", "application/json")
        for k, v in (headers or {}).items(): self.send_header(k, v)
        self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def do_GET(self): self.emit(200, {"endpoints": {"/api/test": {"method": "POST"}}})
    def do_POST(self):
        type(self).posts += 1
        self.rfile.read(int(self.headers.get("Content-Length", "0")))
        value = self.headers.get("PAYMENT-SIGNATURE")
        if not value: self.emit(402, full_challenge()); return
        assert self.account is not None
        envelope = json.loads(base64.b64decode(value)); auth = envelope["payload"]["authorization"]
        address = Account.recover_message(encode_typed_data(full_message=cli.typed_authorization(auth)), signature=envelope["payload"]["signature"])
        type(self).signature_verified = address == self.account.address and auth["to"] == PAYEE and auth["value"] == "50000"
        self.emit(200, {"local_fixture_only": True}, fake_receipt(self.account.address))


class RealLocalHTTPTests(unittest.TestCase):
    def test_real_http_signing_retry_with_ephemeral_unfunded_key(self):
        account = Account.create(); SignedHTTPHandler.account = account
        SignedHTTPHandler.posts = 0; SignedHTTPHandler.signature_verified = False
        server = ThreadingHTTPServer(("127.0.0.1", 0), SignedHTTPHandler); server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            with tempfile.TemporaryDirectory(prefix="raen-http-fixture-") as td:
                result = cli.run_paid(directory(f"http://127.0.0.1:{server.server_port}"), "fixture", "local test",
                                      approved=True, expected_payee=PAYEE, max_amount_atomic="50000",
                                      private_key=account.key, journal_path=Path(td) / "intent.jsonl", allow_loopback=True)
                self.assertTrue(SignedHTTPHandler.signature_verified)
                self.assertEqual(SignedHTTPHandler.posts, 2)
                self.assertTrue(result["server_reported_settlement"])
                self.assertFalse(result["settlement_verified"])
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=2)


if __name__ == "__main__": unittest.main(verbosity=2)
