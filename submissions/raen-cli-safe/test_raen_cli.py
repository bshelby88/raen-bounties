"""Private tests. All HTTP replies below are explicit loopback TEST FIXTURES, not real settlements."""
import base64
import importlib.util
import json
import subprocess
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("raen_cli", HERE / "raen-cli.py")
assert spec is not None and spec.loader is not None
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)
PAYEE = "0x" + "1" * 40


def challenge():
    return {"x402Version": 2, "accepts": [{"scheme": "exact", "network": "eip155:8453", "amount": "50000", "payTo": PAYEE}]}


def directory(endpoint="https://test-service.fly.dev"):
    return {"payTo": PAYEE, "network": "eip155:8453", "services": [{"name": "fixture", "endpoint": endpoint}]}


class PureTests(unittest.TestCase):
    def test_real_twelve_service_manifest(self):
        raw = json.loads((HERE / "official_agents.json").read_text())
        self.assertEqual(len(cli.validate_directory(raw)["services"]), 12)

    def test_duplicate_service_rejected(self):
        doc = directory()
        doc["services"].append(doc["services"][0].copy())
        with self.assertRaises(ValueError): cli.validate_directory(doc)

    def test_credentials_in_url_rejected(self):
        with self.assertRaises(ValueError): cli.validate_url("https://user:pass@test.fly.dev")

    def test_plain_http_rejected(self):
        with self.assertRaises(ValueError): cli.validate_url("http://test.fly.dev")

    def test_loopback_not_allowed_by_default(self):
        with self.assertRaises(ValueError): cli.validate_url("http://127.0.0.1:9000")

    def test_body_challenge_decoded(self):
        self.assertEqual(cli.decode_challenge({}, json.dumps(challenge()).encode())["x402Version"], 2)

    def test_header_challenge_decoded(self):
        encoded = base64.b64encode(json.dumps(challenge()).encode()).decode()
        self.assertEqual(cli.decode_challenge({"Payment-Required": encoded}, b"")["x402Version"], 2)

    def test_boolean_protocol_version_rejected(self):
        c = challenge(); c["x402Version"] = True
        with self.assertRaises(ValueError): cli.decode_challenge({}, json.dumps(c).encode())

    def test_v1_body_amount_supported(self):
        c = {"x402Version": 1, "accepts": [{"scheme": "exact", "network": "base", "maxAmountRequired": "50000", "payTo": PAYEE}]}
        decoded = cli.decode_challenge({}, json.dumps(c).encode())
        self.assertEqual(cli.inspect_requirements(decoded, PAYEE)[0]["amount_atomic"], "50000")

    def test_bad_header_rejected_without_fallback(self):
        with self.assertRaises(ValueError): cli.decode_challenge({"payment-required": "%%%"}, json.dumps(challenge()).encode())

    def test_approved_payee_and_network(self):
        req = cli.inspect_requirements(challenge(), PAYEE)
        self.assertEqual(req[0]["amount_atomic"], "50000")

    def test_wrong_payee_rejected(self):
        with self.assertRaises(ValueError): cli.inspect_requirements(challenge(), "0x" + "3" * 40)

    def test_wrong_network_rejected(self):
        c = challenge(); c["accepts"][0]["network"] = "eip155:1"
        with self.assertRaises(ValueError): cli.inspect_requirements(c, PAYEE)

    def test_noncanonical_amount_rejected(self):
        for amount in ["-1", "0.05", "050000", 50000, "1e5", "0"]:
            with self.subTest(amount=amount):
                c = challenge(); c["accepts"][0]["amount"] = amount
                with self.assertRaises(ValueError): cli.inspect_requirements(c, PAYEE)

    def test_endpoint_cannot_leave_origin(self):
        m = {"endpoints": {"//other.fly.dev/pay": {"method": "POST"}}}
        with self.assertRaises(ValueError): cli.select_endpoint("https://test-service.fly.dev", m)

    def test_malformed_payee_rejected(self):
        d = directory(); d["payTo"] = "0x123"
        with self.assertRaises(ValueError): cli.validate_directory(d)

    def test_unknown_service_does_not_request(self):
        with self.assertRaises(ValueError): cli.run(directory(), "missing", "hello")


class FixtureHandler(BaseHTTPRequestHandler):
    mode = "402"
    posts = 0
    forbidden_headers_seen = []

    def log_message(self, format, *args): pass

    def reply(self, status, body, headers=None):
        encoded = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        for key, value in (headers or {}).items(): self.send_header(key, value)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers(); self.wfile.write(encoded)

    def do_GET(self):
        self.reply(200, {"endpoints": {"/api/fixture": {"method": "POST"}}})

    def do_POST(self):
        type(self).posts += 1
        for key in ("X-PAYMENT", "PAYMENT-SIGNATURE", "Authorization", "Cookie"):
            if self.headers.get(key): type(self).forbidden_headers_seen.append(key)
        self.rfile.read(int(self.headers.get("Content-Length", "0")))
        if self.mode == "redirect": self.reply(302, {}, {"Location": "https://must-not-be-contacted.invalid/"})
        elif self.mode == "200": self.reply(200, {"fixture_only": True, "paid": False})
        else:
            value = base64.b64encode(json.dumps(challenge()).encode()).decode()
            self.reply(402, {"fixture_only": True}, {"payment-required": value})


class LoopbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
        cls.server.daemon_threads = True
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join(timeout=2)

    def setUp(self):
        FixtureHandler.mode = "402"; FixtureHandler.posts = 0; FixtureHandler.forbidden_headers_seen = []

    def test_default_plan_makes_no_post(self):
        result = cli.run(directory(self.url), "fixture", "hello", allow_loopback=True)
        self.assertEqual(result["status"], "planned_only")
        self.assertEqual(FixtureHandler.posts, 0)

    def test_real_loopback_402_stops_without_payment(self):
        result = cli.run(directory(self.url), "fixture", "hello", probe=True, allow_loopback=True)
        self.assertEqual(result["status"], "payment_required_no_payment")
        self.assertEqual(FixtureHandler.posts, 1)
        self.assertEqual(FixtureHandler.forbidden_headers_seen, [])
        self.assertFalse(result["payment_sent"])

    def test_unpaid_200_is_not_called_settled(self):
        FixtureHandler.mode = "200"
        result = cli.run(directory(self.url), "fixture", "hello", probe=True, allow_loopback=True)
        self.assertEqual(result["status"], "unpaid_response")
        self.assertFalse(result["settlement_verified"])

    def test_redirect_not_followed(self):
        FixtureHandler.mode = "redirect"
        result = cli.run(directory(self.url), "fixture", "hello", probe=True, allow_loopback=True)
        self.assertEqual(result["http_status"], 302)
        self.assertEqual(FixtureHandler.posts, 1)


if __name__ == "__main__": unittest.main(verbosity=2)
