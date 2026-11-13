#!/usr/bin/env python3
"""raen-cli.py — One-file Python CLI for the RAEN 12-service x402 fleet."""

import argparse
import base64
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Optional

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
FACILITATOR = "https://facilitator.payai.network"
RAEN_GATEWAY = "https://raen-mcp-gateway.fly.dev"
DEFAULT_WALLET = os.environ.get("RAEN_PRIVATE_KEY", "")
DRY_RUN_FLAG = "--dry-run" in sys.argv

USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
BASE_CHAIN_ID = 8453

# ---------------------------------------------------------------------------
# Keccak-256 (no external deps)
# ---------------------------------------------------------------------------
def keccak256(*datas: bytes) -> bytes:
    h = hashlib.new("sha3_256")
    for d in datas:
        h.update(d)
    return h.digest()

# ---------------------------------------------------------------------------
# RLP-style encoding helpers for EIP-712 / EIP-3009
# ---------------------------------------------------------------------------
def enc_int(n: int) -> bytes:
    return n.to_bytes(32, "big")

def enc_addr(a: str) -> bytes:
    b = bytes.fromhex(a.replace("0x", ""))
    return b.ljust(32, b"\x00")

def enc_str(s: str) -> bytes:
    enc = s.encode()
    if len(enc) <= 55:
        return bytes([0x80 + len(enc)]) + enc
    lb = len(enc).to_bytes(4, "big")
    return bytes([0xb7 + len(lb)]) + lb + enc

# ---------------------------------------------------------------------------
# EIP-712 type hashes
# ---------------------------------------------------------------------------
_AUTH_TYPE_HASH = keccak256(b"TransferWithAuthorization(address from,address to,uint256 value,uint256 validAfter,uint256 validBefore,bytes32 nonce)")
_DOMAIN_TYPE_HASH = keccak256(b"EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)")

def domain_separator() -> bytes:
    return keccak256(_DOMAIN_TYPE_HASH, enc_str("x402MCP"), enc_str("1"),
                     enc_int(BASE_CHAIN_ID), enc_addr(USDC_BASE))

def eip712_struct_hash(from_a: str, to_a: str, value: str,
                        after: int, before: int, nonce: bytes) -> bytes:
    return keccak256(_AUTH_TYPE_HASH, enc_addr(from_a), enc_addr(to_a),
                     enc_int(int(value)), enc_int(after), enc_int(before),
                     nonce if len(nonce) == 32 else nonce + b"\x00" * (32 - len(nonce)))

# ---------------------------------------------------------------------------
# Signing
# ---------------------------------------------------------------------------
def parse_privkey(hexstr: str) -> bytes:
    return bytes.fromhex(hexstr.replace("0x", ""))

def pubaddr_from_priv(privkey: bytes) -> str:
    """Derive Ethereum address — requires cryptography library."""
    try:
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.backends import default_backend
    except ImportError:
        raise RuntimeError("Install cryptography: pip install cryptography eth-account")
    priv = ec.derive_private_key(int.from_bytes(privkey, "big"), ec.SECP256K1(), default_backend())
    pub = priv.public_key()
    unpadded = pub.public_bytes(
        __import__('cryptography.hazmat').formats.Encoding.X962,
        __import__('cryptography.hazmat').formats.PublicFormat.UncompressedPoint
    )
    addr_hash = keccak256(unpadded[1:])
    return "0x" + addr_hash[-20:].hex()

def sign_auth(privkey_hex: str, to_addr: str, value: str,
              valid_after: int, valid_before: int, nonce: bytes) -> tuple[str, str]:
    try:
        from eth_account.messages import encode_defunct
        from eth_account import Account as EthAcc
    except ImportError:
        raise RuntimeError("Install eth_account: pip install eth-account")
    
    pk = "0x" + privkey_hex if not privkey_hex.startswith("0x") else privkey_hex
    acct = EthAcc.from_key(pk)
    msg_hash = eip712_struct_hash(acct.address, to_addr, value,
                                   valid_after, valid_before, nonce)
    signed = acct.signHash(msg_hash)
    return signed.signature.hex(), acct.address

# ---------------------------------------------------------------------------
# HTTP transport
# ---------------------------------------------------------------------------
class X402Client:
    def __init__(self, gateway_url: str = RAEN_GATEWAY,
                 api_key: Optional[str] = None, private_key: str = DEFAULT_WALLET):
        self.gateway = gateway_url.rstrip("/")
        self.api_key = api_key or os.environ.get("RAEN_API_KEY", "")
        self.private_key = private_key
        self.payer_address: Optional[str] = None

    def _req(self, url: str, method="GET", headers=None, body=None, timeout=15):
        req_headers = {"User-Agent": "raen-cli/1.0", "Accept": "application/json"}
        if headers:
            req_headers.update(headers)
        if self.api_key:
            req_headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(url, data=body, headers=req_headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()

    def list_services(self) -> list[dict]:
        url = f"{self.gateway}/.well-known/agent.json"
        status, _, body = self._req(url)
        if status != 200:
            raise RuntimeError(f"agent.json failed: HTTP {status}")
        return json.loads(body)

    def call_tool(self, tool_name: str, args: dict) -> dict:
        url = f"{self.gateway}/mcp"
        payload = json.dumps({
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": args},
            "id": 1,
        }).encode()

        # Step 1: Initial request
        status, hdrs, body = self._req(url, method="POST", body=payload)

        if status == 402:
            payment_req = self._decode_payment_required(hdrs)
            if not payment_req:
                raise RuntimeError("402 without PAYMENT-REQUIRED header")

            print(f"\n[x402] Payment required:")
            res_info = payment_req.get("resource", {})
            print(f"  Resource: {res_info.get('url', '?')}")
            accepts = payment_req.get("accepts", [])
            if accepts:
                opt = accepts[0]
                print(f"  Amount:   {opt.get('amount','?')} atomic ({opt.get('asset','?')[:16]}...)")
                print(f"  Pay-to:   {opt.get('payTo','?')[:20]}...")

            sig, payer = self._sign_payment(payment_req)
            self.payer_address = payer

            payment_payload = self._build_payment(payment_req, sig, payer)
            pay_b64 = base64.b64encode(json.dumps(payment_payload).encode()).decode()

            print(f"  Payer:    {payer}")
            print(f"  Signature: 0x{sig[:16]}... ({len(sig)} hex chars)")

            # Step 3: Resend with signature
            status2, hdrs2, body2 = self._req(
                url, method="POST", body=payload,
                headers={"PAYMENT-SIGNATURE": pay_b64},
            )

            resp_info = self._decode_payment_response(hdrs2)
            if resp_info:
                print(f"\n[x402 Settlement Receipt]:")
                print(f"  Success:     {resp_info.get('success')}")
                tx = resp_info.get('transaction', '')
                if tx:
                    print(f"  Transaction: {tx}")
                print(f"  Network:     {resp_info.get('network')}")
                print(f"  Payer:       {resp_info.get('payer','?')[:20]}...")

            if 200 <= status2 < 300:
                return json.loads(body2)
            else:
                err_text = body2.decode(errors="replace")
                raise RuntimeError(f"After payment: HTTP {status2} — {err_text[:200]}")

        elif 200 <= status < 300:
            return json.loads(body)
        else:
            err_text = body.decode(errors="replace")
            raise RuntimeError(f"HTTP {status}: {err_text[:200]}")

    def _decode_payment_required(self, headers: dict) -> Optional[dict]:
        b64 = headers.get("PAYMENT-REQUIRED") or headers.get("Payment-Required")
        if not b64:
            return None
        try:
            return json.loads(base64.b64decode(b64, validate=True).decode())
        except Exception as e:
            print(f"  [warn] decode PAYMENT-REQUIRED: {e}")
            return None

    def _decode_payment_response(self, headers: dict) -> Optional[dict]:
        b64 = headers.get("PAYMENT-RESPONSE")
        if not b64:
            return None
        try:
            return json.loads(base64.b64decode(b64, validate=True).decode())
        except Exception:
            return None

    def _select_option(self, payment_req: dict) -> dict:
        for opt in payment_req.get("accepts", []):
            if opt.get("scheme") == "exact" and opt.get("network") == "eip155:8453":
                return opt
        accepts = payment_req.get("accepts", [])
        return accepts[0] if accepts else {}

    def _sign_payment(self, payment_req: dict) -> tuple[str, str]:
        if DRY_RUN_FLAG or not self.private_key:
            mock_sig = hashlib.sha256(os.urandom(32)).hexdigest()
            mock_addr = "0x" + hashlib.sha256(os.urandom(20)).hexdigest()
            print(f"  [dry-run] mock sig=0x{mock_sig[:16]}... addr={mock_addr}")
            return mock_sig, mock_addr

        accepted = self._select_option(payment_req)
        if not accepted:
            raise RuntimeError("No acceptable payment options")

        privkey = parse_privkey(self.private_key)
        payer_addr = pubaddr_from_priv(privkey)
        to_addr = accepted.get("payTo", "")
        value = accepted.get("amount", "0")
        now = int(time.time())
        max_to = accepted.get("maxTimeoutSeconds", 60)
        sig, payer = sign_auth(self.private_key, to_addr, value,
                                now, now + min(60, max_to), os.urandom(32))
        return sig, payer

    def _build_payment(self, payment_req: dict, sig: str, payer: str) -> dict:
        accepted = self._select_option(payment_req)
        now = int(time.time())
        max_to = accepted.get("maxTimeoutSeconds", 60)
        return {
            "x402Version": 2,
            "accepted": accepted,
            "payload": {
                "signature": "0x" + sig,
                "authorization": {
                    "from": payer,
                    "to": accepted.get("payTo", ""),
                    "value": accepted.get("amount", "0"),
                    "validAfter": str(now),
                    "validBefore": str(now + min(60, max_to)),
                    "nonce": "0x" + os.urandom(32).hex(),
                },
            },
            "extensions": payment_req.get("extensions", {}),
        }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
SERVICES = ["raen_law_lookup", "raen_ticker_analysis", "raen_dispute_letter",
            "raen_image_generate", "raen_contract_analysis"]

def main():
    ap = argparse.ArgumentParser(prog="raen-cli",
        description="RAEN x402 CLI — pay for AI/legal/finance tools with crypto micropayments")
    ap.add_argument("service", nargs="?", help="Service/tool name")
    ap.add_argument("prompt", nargs="?", help="Prompt argument")
    ap.add_argument("--list", action="store_true", help="List all services")
    ap.add_argument("--dry-run", action="store_true", dest="dry_run",
                    help="Simulate without real signing (default if no key set)")
    ap.add_argument("--key", dest="api_key", help="RAEN gateway Bearer key")
    ap.add_argument("--privkey", dest="private_key", help="Private key for x402 signing")
    ap.add_argument("--json", action="store_true", dest="pretty", help="Pretty-print result")
    args = ap.parse_args()

    if args.list or (not args.service and not args.prompt):
        client = X402Client(api_key=args.api_key)
        try:
            info = client.list_services()
            skills = info.get("skills", [])
            print(f"\n{'='*64}")
            print(f"  RAEN x402 Services  ({len(skills)} tools on Base mainnet)")
            print(f"{'='*64}\n")
            for s in skills:
                sid = s.get("id","?")
                desc = s.get("description","")[:55]
                price = "$0.05" if "dispute" in sid else ("$0.05" if "law" in sid else "$0.01")
                print(f"  {sid:<30}  {price}/call   {desc}")
            print(f"\n  Usage: python raen-cli.py <service> '<prompt>' [--dry-run]")
            print(f"  Examples:")
            for ex in SERVICES[:3]:
                print(f"    python raen-cli.py {ex} 'test prompt' --dry-run")
            print()
        except Exception as e:
            print(f"Error listing services: {e}", file=sys.stderr)
            sys.exit(1)
        return

    if not args.prompt:
        print(f"Usage: python raen-cli.py {args.service} '<prompt>'")
        matching = [s for s in SERVICES if args.service.lower() in s.lower()]
        if matching:
            print(f"\nMatching services: {', '.join(matching)}")
            for m in matching:
                print(f"  python raen-cli.py {m} '<your prompt here>' --dry-run")
        else:
            print(f"\nNo matching service for '{args.service}'. Use --list to see all.")
        sys.exit(0)

    dry = args.dry_run or not (args.private_key or DEFAULT_WALLET)
    client = X402Client(api_key=args.api_key, private_key=args.private_key or DEFAULT_WALLET)
    if dry:
        global DRY_RUN_FLAG
        DRY_RUN_FLAG = True

    print(f"\n{'='*64}")
    print(f"  Tool:      {args.service}")
    print(f"  Prompt:    {args.prompt[:80]}{'...' if len(args.prompt)>80 else ''}")
    print(f"  Dry-run:   {'YES' if dry else 'NO (real signing)'}")
    print(f"{'='*64}")

    try:
        result = client.call_tool(args.service, {"prompt": args.prompt})
        print(f"\n{'='*64}")
        print(f"  Response:")
        print(f"{'='*64}")
        if args.pretty:
            print(json.dumps(result, indent=2, ensure_ascii=False)[:2000])
        else:
            txt = result.get("result", result)
            if isinstance(txt, dict):
                print(json.dumps(txt, indent=2, ensure_ascii=False)[:2000])
            else:
                print(str(txt)[:2000])
        if client.payer_address:
            print(f"\n  Payer wallet: {client.payer_address}")
        print()
    except RuntimeError as e:
        print(f"\n\x1b[31m\x1b[1m✗ Error:\x1b[0m {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
