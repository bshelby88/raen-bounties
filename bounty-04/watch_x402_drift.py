#!/usr/bin/env python3
"""BOUNTY-04: GitHub Action that watches /.well-known/x402.json manifests for scheme/network/payTo drift."""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, List, Optional

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


def extract_payment_entries(manifest: dict) -> List[dict]:
    """Extract payment options (scheme, network, and payTo) from an x402 manifest.

    Supports:
    - Top-level `accepts` (list or dict)
    - Endpoint definitions in `endpoints[path].accepts` (list or dict)
    - Nested methods in `endpoints[path].methods[verb].accepts`
    - Top-level direct keys `scheme`, `network`, `payTo`
    """
    candidates: list[dict] = []

    # 1. Top-level accepts
    if "accepts" in manifest:
        acc = manifest["accepts"]
        if isinstance(acc, list):
            candidates.extend(acc)
        elif isinstance(acc, dict):
            candidates.append(acc)

    # 2. Endpoint mappings
    endpoints = manifest.get("endpoints")
    if isinstance(endpoints, dict):
        for ep_info in endpoints.values():
            if isinstance(ep_info, dict):
                ep_acc = ep_info.get("accepts")
                if isinstance(ep_acc, list):
                    candidates.extend(ep_acc)
                elif isinstance(ep_acc, dict):
                    candidates.append(ep_acc)
                methods = ep_info.get("methods")
                if isinstance(methods, dict):
                    for m_info in methods.values():
                        if isinstance(m_info, dict) and "accepts" in m_info:
                            m_acc = m_info["accepts"]
                            if isinstance(m_acc, list):
                                candidates.extend(m_acc)
                            elif isinstance(m_acc, dict):
                                candidates.append(m_acc)

    # 3. Direct top-level fields
    if "scheme" in manifest or "payTo" in manifest or "pay_to" in manifest:
        candidates.append(manifest)

    entries: list[dict] = []
    seen = set()
    for c in candidates:
        if not isinstance(c, dict):
            continue
        scheme = str(c.get("scheme") or manifest.get("scheme") or "")
        network = str(c.get("network") or manifest.get("network") or "")
        pay_to = str(c.get("payTo") or c.get("pay_to") or manifest.get("payTo") or manifest.get("pay_to") or "")
        key = (scheme, network.lower(), pay_to.lower())
        if key not in seen:
            seen.add(key)
            entries.append({
                "scheme": scheme,
                "network": network,
                "payTo": pay_to,
            })

    if not entries:
        entries.append({
            "scheme": str(manifest.get("scheme") or ""),
            "network": str(manifest.get("network") or ""),
            "payTo": str(manifest.get("payTo") or manifest.get("pay_to") or ""),
        })
    return entries


def compare_manifest(service: str, manifest_url: str, expected: dict, actual_manifest: dict) -> ServiceDriftReport:
    entries = extract_payment_entries(actual_manifest)
    exp_scheme = str(expected.get("scheme", ""))
    exp_net = str(expected.get("network", ""))
    exp_payto = str(expected.get("payTo", ""))

    # Find the matching entry for the expected scheme and network
    selected = None
    for e in entries:
        if (
            (not exp_scheme or e.get("scheme") == exp_scheme)
            and (not exp_net or e.get("network") in (exp_net, exp_net.replace("eip155:8453", "base")))
        ):
            selected = e
            break

    if not selected:
        selected = entries[0] if entries else {"scheme": "", "network": "", "payTo": ""}

    drifts: list[FieldDrift] = []
    for f in MONITORED_FIELDS:
        exp_val = str(expected.get(f, ""))
        act_val = str(selected.get(f, ""))

        # Address comparison is case-insensitive (EIP-55 checksum vs lowercase hex)
        is_same = (exp_val.lower() == act_val.lower()) if f == "payTo" else (exp_val == act_val)
        if not is_same:
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
    retries: int = 2,
) -> tuple[bool, list[ServiceDriftReport]]:
    def default_fetch(url: str, to: int) -> dict:
        import time
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "x402-manifest-drift-watcher/2.0",
                "Accept": "application/json",
            },
        )
        last_exc: Exception | None = None
        for attempt in range(retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=to) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except Exception as exc:
                last_exc = exc
                if attempt < retries:
                    time.sleep(1.5 * (attempt + 1))
        if last_exc:
            raise last_exc
        raise RuntimeError(f"Failed to fetch {url}")

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


def write_step_summary(content: str) -> None:
    """Write markdown summary to GITHUB_STEP_SUMMARY when executing in GitHub Actions."""
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        try:
            with open(summary_path, "a", encoding="utf-8") as f:
                f.write(f"\n{content}\n")
        except Exception as e:
            print(f"[warn] Failed writing to GITHUB_STEP_SUMMARY: {e}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Watch /.well-known/x402.json manifests for drift.")
    ap.add_argument("--config", required=True, help="Path to expected services JSON config")
    ap.add_argument("--timeout", type=int, default=15)
    args = ap.parse_args(argv)

    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    services = cfg.get("services", cfg) if isinstance(cfg, dict) else cfg
    all_ok, reports = check_fleet(services, timeout=args.timeout)
    comment = render_diff_comment(reports)
    print(comment)
    write_step_summary(comment)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
