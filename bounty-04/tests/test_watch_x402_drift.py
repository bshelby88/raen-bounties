"""Unit tests for BOUNTY-04 x402 manifest drift watcher."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import watch_x402_drift as W  # noqa: E402


def test_clean_manifest_passes() -> None:
    expected = [
        {
            "service": "raen-law-lookup",
            "url": "https://law.raen.ai",
            "scheme": "exact",
            "network": "base",
            "payTo": "0x971b573b47357c22a67FcE8c56Aaeb478356C942",
        }
    ]
    ok, reports = W.check_fleet(
        expected,
        fetcher=lambda _u, _t: {
            "accepts": [
                {
                    "scheme": "exact",
                    "network": "base",
                    "payTo": "0x971b573b47357c22a67FcE8c56Aaeb478356C942",
                }
            ]
        },
    )
    assert ok is True
    assert len(reports) == 1
    assert reports[0].drifts == []


def test_case_insensitive_payto_passes() -> None:
    """Verify EIP-55 checksum address vs lowercase address does not trigger false drift."""
    expected = [
        {
            "service": "royal-ruby",
            "url": "https://royal-ruby-x402.fly.dev",
            "scheme": "exact",
            "network": "eip155:8453",
            "payTo": "0x9b8a27e03CEbA490953cDa8AB1291c0E13bAf72f",
        }
    ]
    # Server returns lowercase address
    ok, reports = W.check_fleet(
        expected,
        fetcher=lambda _u, _t: {
            "accepts": [
                {
                    "scheme": "exact",
                    "network": "eip155:8453",
                    "payTo": "0x9b8a27e03ceba490953cda8ab1291c0e13baf72f",
                }
            ]
        },
    )
    assert ok is True
    assert len(reports) == 1
    assert reports[0].drifts == []


def test_multiple_accepts_options_matched() -> None:
    """Check that matching entry is selected when multiple accepts entries are present."""
    expected = [
        {
            "service": "contract-eye",
            "url": "https://contract-eye-x402.fly.dev",
            "scheme": "exact",
            "network": "eip155:8453",
            "payTo": "0x9b8a27e03ceba490953cda8ab1291c0e13baf72f",
        }
    ]
    ok, reports = W.check_fleet(
        expected,
        fetcher=lambda _u, _t: {
            "accepts": [
                {"scheme": "other", "network": "solana", "payTo": "solana-address"},
                {"scheme": "exact", "network": "eip155:8453", "payTo": "0x9b8a27e03ceba490953cda8ab1291c0e13baf72f"},
            ]
        },
    )
    assert ok is True
    assert reports[0].drifts == []


def test_drifted_payto_is_caught_and_diffed() -> None:
    expected = [
        {
            "service": "raen-dispute-letter",
            "url": "https://dispute.raen.ai",
            "scheme": "exact",
            "network": "base",
            "payTo": "0x971b573b47357c22a67FcE8c56Aaeb478356C942",
        }
    ]
    ok, reports = W.check_fleet(
        expected,
        fetcher=lambda _u, _t: {
            "scheme": "exact",
            "network": "base",
            "payTo": "0x000000000000000000000000000000000000dEaD",
        },
    )
    assert ok is False
    assert len(reports[0].drifts) == 1
    assert reports[0].drifts[0].field == "payTo"
    comment = W.render_diff_comment(reports)
    assert "DRIFT DETECTED" in comment
    assert "0x000000000000000000000000000000000000dEaD" in comment


def test_step_summary_output(tmp_path: Path, monkeypatch) -> None:
    """Ensure write_step_summary appends to GITHUB_STEP_SUMMARY file."""
    summary_file = tmp_path / "step_summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))

    W.write_step_summary("### Test Summary Line")
    assert summary_file.exists()
    assert "### Test Summary Line" in summary_file.read_text(encoding="utf-8")


def test_endpoint_level_accepts() -> None:
    """Verify manifests structured with endpoints[path].accepts are parsed correctly."""
    expected = [
        {
            "service": "royal-ruby",
            "url": "https://royal-ruby-x402.fly.dev",
            "scheme": "exact",
            "network": "eip155:8453",
            "payTo": "0x9b8a27e03ceba490953cda8ab1291c0e13baf72f",
        }
    ]
    actual_manifest = {
        "version": "2.0.0",
        "service": {"name": "royal-ruby-x402"},
        "endpoints": {
            "/api/law-lookup": {
                "method": "POST",
                "accepts": {
                    "scheme": "exact",
                    "network": "eip155:8453",
                    "payTo": "0x9b8a27e03ceba490953cda8ab1291c0e13baf72f",
                },
            }
        },
    }
    ok, reports = W.check_fleet(expected, fetcher=lambda _u, _t: actual_manifest)
    assert ok is True
    assert len(reports) == 1
    assert reports[0].drifts == []
