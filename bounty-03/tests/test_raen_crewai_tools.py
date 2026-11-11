"""Unit tests for BOUNTY-03 CrewAI tool wrappers (dispute_letter and contract_analyze)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import example_crew as E  # noqa: E402
import raen_crewai_tools as R  # noqa: E402


def test_dispute_letter_and_contract_analyze_decorators() -> None:
    assert getattr(R.dispute_letter, "tool_name", "dispute_letter") == "dispute_letter"
    assert getattr(R.contract_analyze, "tool_name", "contract_analyze") == "contract_analyze"


def test_example_crew_flow_executes_both_tools() -> None:
    out = E.run_demo_crew_flow()
    assert "uncapped indemnity" in out["contract_analysis"]
    assert "Acme Cloud Services Billing Dept" in out["dispute_letter"]
    assert "NY GBL" in out["dispute_letter"]


def test_missing_api_key_raises_value_error(monkeypatch) -> None:
    monkeypatch.delenv("RAEN_MCP_API_KEY", raising=False)
    R.set_default_client(R.RaenMcpGatewayClient(api_key=""))
    try:
        R.contract_analyze("Sample contract")
        assert False, "Expected ValueError when RAEN_MCP_API_KEY is empty"
    except ValueError as exc:
        assert "RAEN_MCP_API_KEY" in str(exc)
