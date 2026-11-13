"""Unit tests against a local MCP streamable-HTTP fixture (no network, no crewai)."""

import importlib.util
import json
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("raen_crewai_tools", ROOT / "raen_crewai_tools.py")
raen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(raen)

LETTER = json.dumps({
    "letter_body": "Dear Bureau, I dispute this account.",
    "cert_svg": "<svg>ok</svg>",
    "timestamp": "2026-11-10T20:00:00Z",
    "signature": "8a4f9e12",
})
ANALYSIS = json.dumps({"risk_score": 72, "flagged_clauses": ["auto-renew"]})


class FixtureServer:
    """Mimics raen-mcp-gateway: Bearer gate, MCP handshake, tools/call payloads."""

    def __init__(self, sse=False):
        self.sse = sse
        self.calls = []
        self.received = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def respond(self, body, code=200, headers=None):
                raw = b"" if body is None else json.dumps(body).encode()
                self.send_response(code)
                if outer.sse and raw:
                    self.send_header("Content-Type", "text/event-stream")
                    raw = b"data: " + raw + b"\n\n"
                elif raw:
                    self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                for key, value in (headers or {}).items():
                    self.send_header(key, value)
                self.end_headers()
                self.wfile.write(raw)

            def do_POST(self):
                outer.received.append({k.lower(): v for k, v in self.headers.items()})
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                auth = self.headers.get("Authorization", "")
                if auth != "Bearer test-key":
                    self.respond({"error": "Unauthorized. Send Authorization: Bearer <MCP_GATEWAY_KEY>."}, 401)
                    return
                method = payload.get("method")
                if method == "initialize":
                    result = {"protocolVersion": raen.PROTOCOL_VERSION, "capabilities": {"tools": {}},
                              "serverInfo": {"name": "raen-mcp-fixture", "version": "1.0"}}
                    self.respond({"jsonrpc": "2.0", "id": payload["id"], "result": result},
                                 headers={"mcp-session-id": "fixture-session"})
                elif method == "notifications/initialized":
                    assert self.headers.get("mcp-session-id") == "fixture-session"
                    self.respond(None, 202)
                elif method == "tools/call":
                    assert self.headers.get("mcp-session-id") == "fixture-session"
                    outer.calls.append(payload["params"])
                    name = payload["params"]["name"]
                    if name == "raen_dispute_letter":
                        text = LETTER
                    elif name == "raen_contract_analysis":
                        text = ANALYSIS
                    else:
                        self.respond({"jsonrpc": "2.0", "id": payload["id"],
                                      "error": {"code": -32601, "message": "unknown tool"}}, 200)
                        return
                    content = {"jsonrpc": "2.0", "id": payload["id"], "result":
                               {"content": [{"type": "text", "text": text}], "isError": False}}
                    error = {"jsonrpc": "2.0", "id": payload["id"], "result":
                             {"content": [{"type": "text", "text": "402 payment failed"}], "isError": True}}
                    self.respond(error if outer.force_tool_error else content)
                else:
                    self.respond({"error": "unexpected method " + str(method)}, 400)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = "http://127.0.0.1:" + str(self.server.server_port) + "/mcp"
        self.force_tool_error = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()


class ToolTests(unittest.TestCase):
    def client(self, server, **kwargs):
        return raen.RAENGatewayClient(url=server.url, key="test-key", **kwargs)

    @staticmethod
    def invoke(wrapper, **kwargs):
        return getattr(wrapper, "func", wrapper)(**kwargs)  # plain function when crewai absent

    def test_dispute_letter_returns_json_text(self):
        with FixtureServer() as server:
            text = self.client(server).call_tool("raen_dispute_letter",
                                                 {"creditor": "Acme Collections LLC", "reason": "Not my debt"})
            self.assertEqual(json.loads(LETTER), json.loads(text))
            self.assertEqual([{"name": "raen_dispute_letter",
                               "arguments": {"creditor": "Acme Collections LLC", "reason": "Not my debt"}}],
                             server.calls)

    def test_tool_wrappers_pass_documented_arguments(self):
        with FixtureServer() as server:
            env = {"RAEN_MCP_URL": server.url, "RAEN_MCP_KEY": "test-key"}
            with mock.patch.dict(os.environ, env, clear=False):
                self.invoke(raen.raen_dispute_letter, creditor="Acme", reason="Inaccurate")
                self.invoke(raen.raen_contract_analysis, text="terms here")
                self.invoke(raen.raen_contract_analysis, text="terms here", focus="indemnification")
            names = [c["name"] for c in server.calls]
            self.assertEqual(["raen_dispute_letter", "raen_contract_analysis", "raen_contract_analysis"], names)
            self.assertEqual({"text": "terms here"}, server.calls[1]["arguments"])
            self.assertEqual({"text": "terms here", "focus": "indemnification"}, server.calls[2]["arguments"])
            self.assertTrue(all(h.get("authorization") == "Bearer test-key" for h in server.received))

    def test_sse_response_mode(self):
        with FixtureServer(sse=True) as server:
            text = self.client(server).call_tool("raen_contract_analysis", {"text": "t"})
            self.assertEqual(json.loads(ANALYSIS), json.loads(text))

    def test_handshake_order_and_headers(self):
        with FixtureServer() as server:
            self.client(server).call_tool("raen_dispute_letter", {"creditor": "c", "reason": "r"})
            methods = [json.loads(json.dumps(h)) for h in server.received]
            self.assertEqual(3, len(methods))  # initialize, initialized, tools/call — one session
            self.assertIsNone(server.received[0].get("mcp-session-id"))
            self.assertEqual("fixture-session", server.received[1].get("mcp-session-id"))
            self.assertEqual("fixture-session", server.received[2].get("mcp-session-id"))

    def test_missing_key_raises_before_http(self):
        with self.assertRaises(raen.RAENGatewayError) as ctx:
            raen.RAENGatewayClient(url="http://127.0.0.1:1/mcp", key="")
        self.assertIn("RAEN_MCP_KEY", str(ctx.exception))

    def test_bad_key_surfaces_http_401(self):
        with FixtureServer() as server:
            with self.assertRaises(raen.RAENGatewayError) as ctx:
                raen.RAENGatewayClient(url=server.url, key="wrong").call_tool("raen_dispute_letter", {})
            self.assertIn("401", str(ctx.exception))

    def test_mcp_error_response_raises(self):
        with FixtureServer() as server:
            client = self.client(server)
            client.session_id = "fixture-session"  # skip handshake, hit unknown tool directly
            with self.assertRaises(raen.RAENGatewayError) as ctx:
                client.call_tool("raen_no_such_tool", {})
            self.assertIn("-32601", str(ctx.exception))

    def test_is_error_result_raises_with_text(self):
        with FixtureServer() as server:
            server.force_tool_error = True
            with self.assertRaises(raen.RAENGatewayError) as ctx:
                self.client(server).call_tool("raen_dispute_letter", {"creditor": "c", "reason": "r"})
            self.assertIn("402 payment failed", str(ctx.exception))

    def test_unreachable_gateway_raises(self):
        client = raen.RAENGatewayClient(url="http://127.0.0.1:9/mcp", key="test-key")
        with self.assertRaises(raen.RAENGatewayError) as ctx:
            client.call_tool("raen_dispute_letter", {})
        self.assertIn("unreachable", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
