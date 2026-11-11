import importlib.util
import json
import os
import pytest

SPEC = importlib.util.spec_from_file_location(
    "raen_cli",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "raen-cli.py"),
)
raen_cli = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(raen_cli)


def test_fleet_catalog_has_12_services():
    catalog = raen_cli.load_fleet_catalog()
    assert len(catalog) == 12
    ids = {svc["id"] for svc in catalog}
    assert "signal-scanner" in ids
    assert "whale-tracker" in ids
    assert "alpha-synthesizer" in ids


def test_cli_list_flag(capsys):
    rc = raen_cli.main(["--list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "RAEN x402 Fleet (12 Services on Base Mainnet USDC)" in out
    assert "signal-scanner" in out
    assert "alpha-synthesizer" in out


def test_x402_payment_header_generation():
    challenge = {
        "x402Version": 1,
        "accepts": [
            {
                "scheme": "exact",
                "network": "base",
                "maxAmountRequired": "20000",
                "resource": "https://x402.raen.ai/v1/whale-tracker",
                "payTo": "0x971b573b47357c22a67FcE8c56Aaeb478356C942",
                "asset": raen_cli.BASE_USDC_ADDRESS,
            }
        ],
    }
    b64_hdr, payload = raen_cli.build_x402_payment_header(challenge, "0x" + "22" * 32)
    assert isinstance(b64_hdr, str) and len(b64_hdr) > 32
    assert payload["x402Version"] == 1
    assert payload["network"] == "base"
    auth = payload["payload"]["authorization"]
    assert auth["to"] == "0x971b573b47357c22a67FcE8c56Aaeb478356C942"
    assert auth["value"] == "20000"
    assert payload["payload"]["signature"].startswith("0x")


def test_end_to_end_402_challenge_and_settlement(capsys):
    rc = raen_cli.main(["signal-scanner", "Scan top Base momentum tokens", "--simulate", "--json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == 200
    assert out["service"] == "signal-scanner"
    assert out["receipt"]["success"] is True
    assert out["receipt"]["network"] == "base"
    assert out["receipt"]["amountAtomic"] == "10000"
    assert out["receipt"]["txHash"].startswith("0x")
