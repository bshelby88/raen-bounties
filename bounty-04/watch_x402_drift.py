#!/usr/bin/env python3
"""BOUNTY-04: GitHub Action that watches /.well-known/x402.json manifests for scheme/network/payTo drift."""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

MONITORED_FIELDS = ("scheme", "network", "payTo")


@dataclass(frozen=True)
class FieldDrift:
    field: str
    expected: str
    actual: str


@dataclass(frozen=True)
class ServiceDriftReport:
    service: str
    manifest_url: str
    ok: bool
    drifts: list[FieldDrift]
    error: str | None = None


def extract_payment_entry(manifest: dict) -> dict:
    """Extract scheme, network, and payTo from an x402 manifest (supports top-level or accepts[0])."""
    accepts = manifest.get("accepts")
    if isinstance(accepts, list) and accepts and isinstance(accepts[0], dict):
        first = accepts[0]
        return {
            "scheme": str(first.get("scheme") or manifest.get("scheme") or ""),
            "network": str(first.get("network") or manifest.get("network") or ""),
            "payTo": str(first.get("payTo") or first.get("pay_to") or manifest.get("payTo") or ""),
        }
    return {
        "scheme": str(manifest.get("scheme") or ""),
        "network": str(manifest.get("network") or ""),
        "payTo": str(manifest.get("payTo") or manifest.get("pay_to") or ""),
    }


def compare_manifest(service: str, manifest_url: str, expected: dict, actual_manifest: dict) -> ServiceDriftReport:
    actual = extract_payment_entry(actual_manifest)
    drifts: list[FieldDrift] = []
    for f in MONITORED_FIELDS:
        exp_val = str(expected.get(f, ""))
        act_val = str(actual.get(f, ""))
        if exp_val != act_val:
            drifts.append(FieldDrift(field=f, expected=exp_val, actual=act_val))
    return ServiceDriftReport(
        service=service,
        manifest_url=manifest_url,
        ok=(len(drifts) == 0),
        drifts=drifts,
        error=None,
    )


def render_diff_comment(reports: list[ServiceDriftReport]) -> str:
    failing = [r for r in reports if not r.ok]
    if not failing:
        return "### x402 Manifest Drift Watcher: PASS\n\nAll monitored `/.well-known/x402.json` manifests match expected `scheme`, `network`, and `payTo` values."

    lines = [
        "### x402 Manifest Drift Watcher: DRIFT DETECTED",
        "",
        "| Service | Manifest URL | Field | Expected | Actual |",
        "|---|---|---|---|---|",
    ]
    for r in failing:
        if r.error:
            lines.append(f"| `{r.service}` | `{r.manifest_url}` | `HTTP/JSON` | `200 OK` | `{r.error}` |")
        for d in r.drifts:
            lines.append(f"| `{r.service}` | `{r.manifest_url}` | `{d.field}` | `{d.expected}` | `{d.actual}` |")
    return "\n".join(lines)


def check_fleet(
    expected_services: list[dict],
    fetcher: Callable[[str, int], dict] | None = None,
    timeout: int = 15,
) -> tuple[bool, list[ServiceDriftReport]]:
    def default_fetch(url: str, to: int) -> dict:
        req = urllib.request.Request(url, headers={"User-Agent": "x402-manifest-drift-watcher/1.0"})
        with urllib.request.urlopen(req, timeout=to) as resp:
            return json.loads(resp.read().decode("utf-8"))

    fetch_fn = fetcher or default_fetch
    reports: list[ServiceDriftReport] = []
    for entry in expected_services:
        svc = entry["service"]
        base_url = entry["url"].rstrip("/")
        manifest_url = base_url if base_url.endswith("x402.json") else f"{base_url}/.well-known/x402.json"
        try:
            actual_manifest = fetch_fn(manifest_url, timeout)
            reports.append(compare_manifest(svc, manifest_url, entry, actual_manifest))
        except Exception as exc:
            reports.append(
                ServiceDriftReport(
                    service=svc,
                    manifest_url=manifest_url,
                    ok=False,
                    drifts=[],
                    error=str(exc),
                )
            )
    all_ok = all(r.ok for r in reports)
    return all_ok, reports


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Watch /.well-known/x402.json manifests for drift.")
    ap.add_argument("--config", required=True, help="Path to expected services JSON config")
    ap.add_argument("--timeout", type=int, default=15)
    args = ap.parse_args(argv)

    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    services = cfg.get("services", cfg) if isinstance(cfg, dict) else cfg
    all_ok, reports = check_fleet(services, timeout=args.timeout)
    print(render_diff_comment(reports))
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
