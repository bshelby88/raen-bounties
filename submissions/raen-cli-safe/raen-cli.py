#!/usr/bin/env python3
"""RAEN private client: default unpaid discovery; explicit opt-in EIP-3009 signing.

Signing and one-retry protocol handling are implemented, but real payment and
mainnet settlement remain unexecuted. Defaults never load keys or send payment.
"""
import argparse
import base64
import binascii
import hashlib
import json
import os
import secrets
import time
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

DIRECTORY_URL = "https://bshelby88.github.io/raen-agent-directory/agents.json"
MAX_BYTES = 2_000_000
ADDRESS = re.compile(r"0x[0-9a-fA-F]{40}\Z")
AMOUNT = re.compile(r"[1-9][0-9]{0,77}\Z")
SERVICE = re.compile(r"[a-z0-9][a-z0-9-]{0,79}\Z")


def validate_url(url, allow_loopback=False):
    if not isinstance(url, str) or any(ord(c) < 33 for c in url):
        raise ValueError("invalid URL")
    p = urllib.parse.urlsplit(url)
    if p.username is not None or p.password is not None or p.fragment:
        raise ValueError("URL credentials and fragments are forbidden")
    if p.port is not None and not (1 <= p.port <= 65535):
        raise ValueError("invalid port")
    local = p.hostname in {"127.0.0.1", "localhost", "::1"}
    if local and allow_loopback and p.scheme == "http": return url
    if local or p.scheme != "https" or not p.hostname:
        raise ValueError("HTTPS required; loopback requires the explicit test flag")
    if not (p.hostname.endswith(".fly.dev") or p.hostname == "bshelby88.github.io"):
        raise ValueError("host outside this prototype's reviewed RAEN allowlist")
    return url


def validate_directory(doc, allow_loopback=False):
    if not isinstance(doc, dict) or not ADDRESS.fullmatch(str(doc.get("payTo", ""))):
        raise ValueError("missing or malformed directory payTo")
    if doc.get("network") != "eip155:8453":
        raise ValueError("this prototype accepts only the declared Base network")
    rows = doc.get("services")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 100:
        raise ValueError("invalid services list")
    services = {}
    for row in rows:
        if not isinstance(row, dict): raise ValueError("invalid service record")
        name, endpoint = row.get("name"), row.get("endpoint")
        if not isinstance(name, str) or not SERVICE.fullmatch(name) or name in services:
            raise ValueError("invalid or duplicate service name")
        services[name] = validate_url(endpoint, allow_loopback)
    return {"pay_to": doc["payTo"], "network": doc["network"], "services": services}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs): return None


def request(url, data=None, allow_loopback=False, payment_header=None):
    validate_url(url, allow_loopback)
    headers = {"Accept": "application/json", "User-Agent": "RAEN-private-no-payment-client/0.1"}
    if data is not None: headers["Content-Type"] = "application/json"
    if payment_header is not None:
        key, value = payment_header
        if key not in {"X-PAYMENT", "PAYMENT-SIGNATURE"} or not isinstance(value, str) or len(value) > 100000:
            raise ValueError("invalid payment header")
        headers[key] = value
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data is not None else "GET")
    opener = urllib.request.build_opener(NoRedirect())
    try: response = opener.open(req, timeout=15)
    except urllib.error.HTTPError as error: response = error
    with response:
        body = response.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES: raise ValueError("response size limit exceeded")
        return response.code, dict(response.headers.items()), body


def parse_json(raw):
    try: return json.loads(raw)
    except (ValueError, UnicodeError, TypeError) as error:
        raise ValueError("invalid JSON response") from error


def decode_challenge(headers, body):
    lowered = {k.lower(): v for k, v in headers.items()}
    encoded = lowered.get("payment-required")
    if encoded is not None:
        if not isinstance(encoded, str) or len(encoded) > 100_000:
            raise ValueError("invalid payment-required header")
        try: raw = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as error:
            raise ValueError("invalid payment-required base64") from error
        obj = parse_json(raw)
    else: obj = parse_json(body)
    if not isinstance(obj, dict): raise ValueError("challenge must be an object")
    version = obj.get("x402Version")
    if type(version) is not int or version not in (1, 2):
        raise ValueError("unsupported x402 version")
    return obj


def inspect_requirements(challenge, expected_payee):
    if not ADDRESS.fullmatch(str(expected_payee)):
        raise ValueError("invalid expected payee")
    accepts = challenge.get("accepts")
    if not isinstance(accepts, list) or not 1 <= len(accepts) <= 100:
        raise ValueError("missing payment requirements")
    out = []
    for req in accepts:
        if not isinstance(req, dict): continue
        payee = req.get("payTo")
        amount = req.get("amount", req.get("maxAmountRequired"))
        if req.get("scheme") != "exact" or req.get("network") not in {"eip155:8453", "base"}: continue
        if not isinstance(payee, str) or not ADDRESS.fullmatch(payee): continue
        if payee.lower() != expected_payee.lower(): continue
        if not isinstance(amount, str) or not AMOUNT.fullmatch(amount): continue
        # Preserve observed values; a challenge is not a payment authorization.
        out.append({"scheme": req["scheme"], "network": req["network"], "payTo": payee,
                    "amount_atomic": amount, "asset": req.get("asset"), "resource": req.get("resource")})
    if not out: raise ValueError("no exact Base requirement matches the expected payee and canonical positive amount")
    return out


def select_endpoint(base, manifest, endpoint=None, allow_loopback=False):
    if not isinstance(manifest, dict) or not isinstance(manifest.get("endpoints"), dict):
        raise ValueError("service manifest has no endpoints")
    endpoints = manifest["endpoints"]
    choices = [p for p, meta in endpoints.items() if isinstance(meta, dict) and meta.get("method") == "POST"]
    if endpoint is None:
        if len(choices) != 1: raise ValueError("select an explicit manifest POST endpoint")
        endpoint = choices[0]
    if endpoint not in choices or not endpoint.startswith("/") or endpoint.startswith("//"):
        raise ValueError("invalid manifest endpoint")
    url = urllib.parse.urljoin(base.rstrip("/") + "/", endpoint)
    a, b = urllib.parse.urlsplit(base), urllib.parse.urlsplit(url)
    if (a.scheme, a.netloc) != (b.scheme, b.netloc): raise ValueError("endpoint leaves service origin")
    return validate_url(url, allow_loopback)


def run(directory, service, prompt, probe=False, allow_loopback=False, payload=None, endpoint=None):
    config = validate_directory(directory, allow_loopback)
    if service not in config["services"]: raise ValueError("unknown service")
    if not isinstance(prompt, str) or not prompt or len(prompt) > 100_000:
        raise ValueError("prompt must contain 1 to100000 characters")
    base = config["services"][service]
    common = {"service": service, "payment_sent": False, "settlement_verified": False}
    if not probe: return {**common, "status": "planned_only", "base_url": base, "request_sent": False}
    status, _, raw = request(base.rstrip("/") + "/.well-known/x402.json", allow_loopback=allow_loopback)
    if status != 200: raise ValueError("service manifest fetch failed")
    url = select_endpoint(base, parse_json(raw), endpoint, allow_loopback)
    request_data = {"prompt": prompt} if payload is None else payload
    if not isinstance(request_data, dict): raise ValueError("request JSON must be an object")
    data = json.dumps(request_data, ensure_ascii=False).encode()
    if len(data) > MAX_BYTES: raise ValueError("request body too large")
    status, headers, body = request(url, data=data, allow_loopback=allow_loopback)
    result = {**common, "http_status": status, "request_sent": True, "response_sha256": hashlib.sha256(body).hexdigest()}
    if status == 402:
        obj = decode_challenge(headers, body)
        return {**result, "status": "payment_required_no_payment", "x402_version": obj["x402Version"],
                "requirements": inspect_requirements(obj, config["pay_to"])}
    return {**result, "status": "unpaid_response" if 200 <= status < 300 else "upstream_error"}


# Base USDC policy pinned to the organizer's preserved cookbook and agents.json.
USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"


def typed_authorization(authorization, asset=USDC_BASE):
    return {
        "types": {
            "EIP712Domain": [{"name": "name", "type": "string"}, {"name": "version", "type": "string"},
                             {"name": "chainId", "type": "uint256"}, {"name": "verifyingContract", "type": "address"}],
            "TransferWithAuthorization": [{"name": "from", "type": "address"}, {"name": "to", "type": "address"},
                                          {"name": "value", "type": "uint256"}, {"name": "validAfter", "type": "uint256"},
                                          {"name": "validBefore", "type": "uint256"}, {"name": "nonce", "type": "bytes32"}],
        },
        "primaryType": "TransferWithAuthorization",
        "domain": {"name": "USD Coin", "version": "2", "chainId": 8453, "verifyingContract": asset},
        "message": authorization,
    }


def prepare_payment_header(challenge, expected_payee, max_amount_atomic, private_key, now=None):
    """Sign a bounded EIP-3009 authorization in memory. Never print or journal this return value."""
    version = challenge.get("x402Version")
    if type(version) is not int or version not in (1, 2): raise ValueError("unsupported version")
    if not isinstance(max_amount_atomic, str) or not AMOUNT.fullmatch(max_amount_atomic):
        raise ValueError("explicit canonical positive spending cap required")
    summaries = inspect_requirements(challenge, expected_payee)
    selected = None
    for item in challenge["accepts"]:
        if not isinstance(item, dict): continue
        amount = item.get("amount", item.get("maxAmountRequired"))
        if not any(s["network"] == item.get("network") and s["payTo"] == item.get("payTo") and s["amount_atomic"] == amount for s in summaries): continue
        if not isinstance(item.get("asset"), str) or item["asset"].lower() != USDC_BASE.lower(): continue
        if not isinstance(amount, str) or not AMOUNT.fullmatch(amount): continue
        if int(amount) > int(max_amount_atomic) or int(amount) >= 1 << 256: continue
        selected = item
        break
    if selected is None: raise ValueError("asset or spending cap mismatch")
    extra = selected.get("extra") or {}
    if isinstance(extra, str): extra = parse_json(extra)
    if not isinstance(extra, dict): raise ValueError("invalid token domain metadata")
    if extra.get("assetTransferMethod") not in (None, "eip3009"):
        raise ValueError("unsupported transfer method; no Permit2 fallback")
    if extra.get("name", "USD Coin") != "USD Coin" or extra.get("version", "2") != "2":
        raise ValueError("token domain differs from pinned Base USDC policy")
    timeout = selected.get("maxTimeoutSeconds", 600)
    if type(timeout) is not int or timeout <= 0: raise ValueError("invalid expiry")
    timeout = min(timeout, 600)
    timestamp = int(time.time()) if now is None else now
    if type(timestamp) is not int or timestamp < 600: raise ValueError("invalid clock")
    from eth_account import Account  # Only direct non-stdlib dependency; imported only for explicit signing.
    account = Account.from_key(private_key)
    amount = selected.get("amount", selected.get("maxAmountRequired"))
    authorization = {"from": account.address, "to": selected["payTo"], "value": amount,
                     "validAfter": str(timestamp - 600 if version == 1 else 0),
                     "validBefore": str(timestamp + timeout), "nonce": "0x" + secrets.token_hex(32)}
    signed = Account.sign_typed_data(private_key, full_message=typed_authorization(authorization))
    signature = "0x" + bytes(signed.signature).hex()
    payload = {"signature": signature, "authorization": authorization}
    if version == 1:
        envelope = {"x402Version": 1, "scheme": "exact", "network": selected["network"], "payload": payload}
    else:
        envelope = {"x402Version": 2, "accepted": selected, "payload": payload}
        if "resource" in challenge: envelope["resource"] = challenge["resource"]
    encoded = base64.b64encode(json.dumps(envelope, separators=(",", ":")).encode()).decode()
    return {"header_name": "X-PAYMENT" if version == 1 else "PAYMENT-SIGNATURE", "value": encoded,
            "payer": account.address, "amount_atomic": amount, "network": selected["network"]}


def settlement_response(headers, expected_payer):
    """Check the provider's receipt shape. This is NOT independent chain confirmation."""
    lowered = {k.lower(): v for k, v in headers.items()}
    value = lowered.get("payment-response", lowered.get("x-payment-response"))
    if not isinstance(value, str) or len(value) > 100000: raise ValueError("missing settlement receipt")
    try: raw = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as error: raise ValueError("invalid receipt encoding") from error
    receipt = parse_json(raw)
    if not isinstance(receipt, dict) or receipt.get("success") is not True: raise ValueError("unsuccessful receipt")
    if receipt.get("network") not in {"base", "eip155:8453"}: raise ValueError("receipt network mismatch")
    if not isinstance(receipt.get("transaction"), str) or not re.fullmatch(r"0x[0-9a-fA-F]{64}", receipt["transaction"]):
        raise ValueError("invalid receipt transaction hash")
    payer = receipt.get("payer")
    if payer is not None and (not isinstance(payer, str) or payer.lower() != expected_payer.lower()):
        raise ValueError("receipt payer mismatch")
    return {k: receipt[k] for k in ("success", "network", "transaction", "payer") if k in receipt}


def run_paid(directory, service, prompt, *, approved, expected_payee, max_amount_atomic,
             private_key, journal_path, payload=None, endpoint=None, allow_loopback=False):
    """One unsigned challenge and at most ONE signed retry. No automatic retry after uncertain outcome."""
    if approved is not True: raise ValueError("explicit payment approval required")
    config = validate_directory(directory, allow_loopback)
    if not ADDRESS.fullmatch(str(expected_payee)) or config["pay_to"].lower() != expected_payee.lower():
        raise ValueError("expected payee must independently match the directory")
    if service not in config["services"]: raise ValueError("unknown service")
    if not isinstance(prompt, str) or not prompt or len(prompt) > 100000: raise ValueError("invalid prompt")
    base = config["services"][service]
    status, _, raw = request(base.rstrip("/") + "/.well-known/x402.json", allow_loopback=allow_loopback)
    if status != 200: raise ValueError("manifest unavailable")
    url = select_endpoint(base, parse_json(raw), endpoint, allow_loopback)
    value = {"prompt": prompt} if payload is None else payload
    if not isinstance(value, dict): raise ValueError("request must be an object")
    data = json.dumps(value, ensure_ascii=False).encode()
    if len(data) > MAX_BYTES: raise ValueError("request too large")
    status, headers, body = request(url, data=data, allow_loopback=allow_loopback)
    if status != 402:
        return {"status": "no_payment_challenge", "http_status": status, "payment_attempted": False,
                "settlement_verified": False}
    prepared = prepare_payment_header(decode_challenge(headers, body), expected_payee, max_amount_atomic, private_key)
    # A new, exclusive, owner-controlled intent journal precedes the irreversible signed request.
    target = Path(journal_path)
    if not target.parent.is_dir() or target.parent.stat().st_mode & 0o022:
        raise ValueError("intent journal requires a non-group/world-writable parent")
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    log = os.fdopen(fd, "w", encoding="utf-8")
    try:
        log.write(json.dumps({"state": "SIGNED_REQUEST_PENDING", "service": service,
                              "request_sha256": hashlib.sha256(data).hexdigest(),
                              "header_sha256": hashlib.sha256(prepared["value"].encode()).hexdigest(),
                              "amount_atomic": prepared["amount_atomic"], "network": prepared["network"]}) + "\n")
        log.flush(); os.fsync(log.fileno())
    except Exception:
        log.close()
        raise
    result: dict[str, object] = {"payment_attempted": True, "settlement_verified": False, "automatic_retry": False}
    try:
        status, headers, body = request(url, data=data, allow_loopback=allow_loopback,
                                       payment_header=(prepared["header_name"], prepared["value"]))
        result["http_status"] = status
        if 200 <= status < 300:
            receipt = settlement_response(headers, prepared["payer"])
            result.update(status="provider_reported_settlement", server_reported_settlement=True, receipt=receipt)
        else: result.update(status="signed_request_rejected_no_retry", server_reported_settlement=False)
    except Exception:
        # Submission may already have reached the provider. Never assert 'no payment' or send a second nonce.
        result.update(status="payment_outcome_unknown_no_retry", server_reported_settlement=False)
    try:
        log.write(json.dumps(result) + "\n"); log.flush(); os.fsync(log.fileno())
    except OSError: result["journal_update_failed"] = True
    finally:
        try: log.close()
        except OSError: result["journal_update_failed"] = True
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description="RAEN single-file client; default no payment; explicit signing opt-in only")
    p.add_argument("service", nargs="?", default="list")
    p.add_argument("prompt", nargs="?")
    p.add_argument("--directory", default=str(Path(__file__).with_name("official_agents.json")))
    p.add_argument("--probe", action="store_true")
    p.add_argument("--endpoint")
    p.add_argument("--request-json")
    p.add_argument("--allow-loopback-test", action="store_true")
    p.add_argument("--pay", action="store_true", help="Requires separate owner approval, cap, payee and new journal")
    p.add_argument("--max-amount-atomic")
    p.add_argument("--expected-pay-to")
    p.add_argument("--journal")
    a = p.parse_args(argv)
    try:
        if a.directory.startswith("https://"):
            status, _, raw = request(a.directory)
            if status != 200: raise ValueError("directory unavailable")
        else: raw = Path(a.directory).read_bytes()
        if len(raw) > MAX_BYTES: raise ValueError("directory too large")
        d = parse_json(raw)
        if a.pay:
            if a.service == "list" or a.probe or os.environ.get("RAEN_PAYMENT_APPROVED") != "YES":
                raise ValueError("payment mode not approved")
            if not a.expected_pay_to or not a.max_amount_atomic or not a.journal:
                raise ValueError("explicit independent payment policy and new journal required")
            key = os.environ.get("RAEN_PRIVATE_KEY")
            if not key: raise ValueError("owner-supplied signer unavailable")
            body = parse_json(a.request_json) if a.request_json else None
            result = run_paid(d, a.service, a.prompt, approved=True, expected_payee=a.expected_pay_to,
                              max_amount_atomic=a.max_amount_atomic, private_key=key, journal_path=a.journal,
                              payload=body, endpoint=a.endpoint, allow_loopback=a.allow_loopback_test)
            del key
        elif a.service == "list":
            conf = validate_directory(d, a.allow_loopback_test)
            result = {"services": [{"name": k, "endpoint": v} for k, v in conf["services"].items()],
                      "service_count": len(conf["services"]), "payment_enabled": False}
        else:
            body = parse_json(a.request_json) if a.request_json else None
            result = run(d, a.service, a.prompt, a.probe, a.allow_loopback_test, body, a.endpoint)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        if result.get("status") == "payment_required_no_payment": return 2
        if result.get("status") in {"upstream_error", "payment_outcome_unknown_no_retry", "signed_request_rejected_no_retry"}: return 4
        return 0
    except (ValueError, OSError, ImportError, urllib.error.URLError):
        print(json.dumps({"error": "preflight_or_request_failed", "settlement_verified": False}), file=sys.stderr)
        return 3


if __name__ == "__main__": raise SystemExit(main())
