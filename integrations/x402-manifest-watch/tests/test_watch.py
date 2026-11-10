from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("watch", ROOT / "watch.py")
watch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watch)
EXPECTED = {"scheme": "exact", "network": "eip155:8453", "payTo": "0x" + "a1" * 20}


class WatchTests(unittest.TestCase):
    def test_raen_endpoints_object_and_array(self):
        self.assertEqual(2, len(watch.payment_options({"endpoints": {"/one": {"accepts": EXPECTED}, "/two": {"accepts": [EXPECTED]}}})))

    def test_top_level_and_error_arrays(self):
        for body in [{"accepts": [EXPECTED]}, {"error": {"accepts": [EXPECTED]}}]:
            self.assertEqual([EXPECTED], list(watch.payment_options(body).values()))

    def test_casing_is_not_payment_drift(self):
        payment = {**EXPECTED, "payTo": "0x" + "A1" * 20}
        checked, failures = watch.check_services([("test", "https://example.test", EXPECTED)], lambda _: {"accepts": [payment]})
        self.assertEqual((1, []), (checked, failures))

    def test_each_field_drifts(self):
        for field, value in [("scheme", "other"), ("network", "eip155:1"), ("payTo", "0x" + "bb" * 20)]:
            with self.subTest(field=field):
                checked, failures = watch.check_services([("test", "https://example.test", EXPECTED)], lambda _: {"accepts": [{**EXPECTED, field: value}]})
                self.assertEqual(0, checked)
                self.assertEqual(1, len(failures))
                self.assertIn('-    "' + field + '"', failures[0])
                self.assertIn('+    "' + field + '"', failures[0])

    def test_checks_second_option_and_later_endpoint(self):
        for body in [{"accepts": [EXPECTED, {**EXPECTED, "network": "wrong"}]}, {"endpoints": {"/a": {"accepts": EXPECTED}, "/b": {"accepts": {**EXPECTED, "network": "wrong"}}}}]:
            self.assertTrue(watch.check_services([("test", "https://example.test", EXPECTED)], lambda _: body)[1])

    def test_missing_empty_and_invalid_fields_fail(self):
        bodies = [{}, {"accepts": []}, {"accepts": [None]}, {"endpoints": {}}, {"endpoints": {"/one": {}}}, {"accepts": [{**EXPECTED, "payTo": "0x0"}]}]
        for field in EXPECTED:
            payment = dict(EXPECTED); del payment[field]; bodies.append({"accepts": payment})
        for body in bodies:
            with self.subTest(body=body):
                checked, failures = watch.check_services([("test", "https://example.test", EXPECTED)], lambda _: body)
                self.assertEqual(0, checked); self.assertEqual(1, len(failures))

    def test_unavailable_service_does_not_skip_remaining_services(self):
        seen = []
        def fetch(url):
            seen.append(url)
            if url.endswith("bad"):raise HTTPError(url, 404, "Not Found", {}, None)
            return {"accepts": EXPECTED}
        checked, failures = watch.check_services([("bad", "https://example.test/bad", EXPECTED), ("good", "https://example.test/good", EXPECTED)], fetch)
        self.assertEqual(2, len(seen)); self.assertEqual(1, checked); self.assertIn("404", failures[0])

    def test_configuration_requires_nonempty_unique_services(self):
        service = {"name": "a", "url": "https://example.test/manifest"}
        for services in [[], [service, service]]:
            with self.assertRaises(ValueError):watch.config_services({"expected": EXPECTED, "services": services})

    def test_local_http_needs_explicit_fixture_flag(self):
        config = {"expected": EXPECTED, "services": [{"name": "test", "url": "http://127.0.0.1/manifest"}]}
        with self.assertRaises(ValueError):watch.config_services(config)
        self.assertEqual(1, len(watch.config_services(config, True)))
        config["services"][0]["url"] = "http://example.test/manifest"
        with self.assertRaises(ValueError):watch.config_services(config, True)

    def test_expected_service_override(self):
        config = {"expected": EXPECTED, "services": [{"name": "test", "url": "https://example.test", "expected": {"network": "eip155:1"}}]}
        self.assertEqual("eip155:1", watch.config_services(config)[0][2]["network"])

    def test_report_cannot_break_out_of_diff_fence(self):
        body = watch.report_text(0, 1, ["bad\n```\nuntrusted"])
        self.assertIn("````diff\n", body); self.assertTrue(body.endswith("````"))

    def test_comment_pagination_updates_own_bot_only(self):
        calls = []
        def request(url, **kw):
            calls.append((url, kw))
            if "&page=1" in url:return [{"user": {"login": "someone"}, "body": watch.MARKER}] * 100
            if "&page=2" in url:return [{"id": 7, "user": {"login": "github-actions[bot]"}, "body": watch.MARKER + "old"}]
            return {}
        watch.sync_comment("owner/repo", 4, "test", "new", True, request=request)
        self.assertEqual(3, len(calls)); self.assertEqual("PATCH", calls[-1][1]["method"])
        self.assertTrue(calls[-1][0].endswith("/issues/comments/7"))

    def test_identical_comment_is_not_written_again(self):
        calls = []
        def request(url, **kw):
            calls.append(kw)
            return [{"id": 7, "user": {"login": "github-actions[bot]"}, "body": watch.MARKER}]
        watch.sync_comment("owner/repo", 4, "test", watch.MARKER, True, request=request)
        self.assertEqual(1, len(calls))

    def test_healthy_run_does_not_open_comment(self):
        calls = []
        def request(url, **kw):calls.append(kw); return []
        watch.sync_comment("owner/repo", 4, "test", watch.MARKER, False, request=request)
        self.assertEqual(1, len(calls))

    def test_comment_error_propagates(self):
        def request(*args, **kw):raise HTTPError("https://api.github.com", 403, "Forbidden", {}, None)
        with self.assertRaises(HTTPError):watch.sync_comment("owner/repo", 4, "test", watch.MARKER, True, request=request)


class FixtureServer:
    def __enter__(self):
        self.comments = []; self.requests = []; self.payment = dict(EXPECTED)
        outer = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):pass
            def respond(self, body, code=200):
                raw = json.dumps(body).encode(); self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)
            def do_GET(self):
                outer.requests.append(("GET", self.path))
                if self.path == "/.well-known/x402.json":self.respond({"endpoints": {"/api/demo": {"accepts": outer.payment}}})
                elif self.path.startswith("/repos/example/demo/issues/4/comments?"):self.respond(outer.comments)
                else:self.respond({"error": "unexpected route"}, 404)
            def do_POST(self):
                outer.requests.append(("POST", self.path)); payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if self.path != "/repos/example/demo/issues/4/comments":self.respond({}, 404); return
                outer.comments.append({"id": 1, "user": {"login": "github-actions[bot]"}, **payload}); self.respond(outer.comments[-1], 201)
            def do_PATCH(self):
                outer.requests.append(("PATCH", self.path)); payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if self.path != "/repos/example/demo/issues/comments/1":self.respond({}, 404); return
                outer.comments[0].update(payload); self.respond(outer.comments[0])
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.url = "http://127.0.0.1:" + str(self.server.server_port)
        self.temp = tempfile.TemporaryDirectory(); self.config = Path(self.temp.name) / "fleet.json"
        self.config.write_text(json.dumps({"expected": EXPECTED, "services": [{"name": "fixture-service", "url": self.url + "/.well-known/x402.json"}]}))
        return self
    def run(self):
        env = os.environ.copy()
        for key in ["GITHUB_EVENT_PATH", "GITHUB_STEP_SUMMARY"]:env.pop(key, None)
        env.update(X402_ISSUE="4", X402_TOKEN="fixture-token", GITHUB_REPOSITORY="example/demo", GITHUB_API_URL=self.url)
        return subprocess.run([sys.executable, str(ROOT / "watch.py"), "--config", str(self.config), "--allow-local-http"], capture_output=True, text=True, env=env, timeout=15)
    def __exit__(self, *args):
        self.server.shutdown(); self.server.server_close(); self.thread.join(); self.temp.cleanup()


class IntegrationTests(unittest.TestCase):
    def test_bad_payto_fails_and_comments_then_resolves_without_duplicates(self):
        with FixtureServer() as server:
            server.payment["payTo"] = "0x" + "bb" * 20
            bad = server.run(); self.assertEqual(1, bad.returncode, bad.stderr)
            self.assertIn("payTo", server.comments[0]["body"])
            self.assertIn("0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", bad.stdout)
            self.assertEqual(1, len(server.comments)); self.assertEqual(1, server.run().returncode)
            self.assertEqual(1, len(server.comments))
            server.payment = dict(EXPECTED)
            self.assertEqual(0, server.run().returncode)
            self.assertIn("1/1 services match", server.comments[0]["body"])
            self.assertEqual(1, len(server.comments))
            self.assertTrue(all(path.startswith("/.well-known/") or path.startswith("/repos/example/demo/issues/") for _, path in server.requests))


if __name__ == "__main__":unittest.main()
