#!/usr/bin/env python3
"""Example CrewAI flow demonstrating contract_analyze and dispute_letter via RAEN MCP Gateway."""
from __future__ import annotations

import json
from typing import Any

from raen_crewai_tools import (
    RaenMcpGatewayClient,
    contract_analyze,
    dispute_letter,
    set_default_client,
)


def run_demo_crew_flow() -> dict[str, str]:
    def demo_transport(_url: str, _headers: dict[str, str], body: bytes) -> dict[str, Any]:
        req = json.loads(body.decode("utf-8"))
        name = req["params"]["name"]
        args = req["params"]["arguments"]
        if name == "contract_analyze":
            return {
                "jsonrpc": "2.0",
                "id": req["id"],
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": f"[RAEN contract_analyze] High-risk uncapped indemnity and 60-day silent auto-renewal detected ({args['jurisdiction']}).",
                        }
                    ]
                },
            }
        return {
            "jsonrpc": "2.0",
            "id": req["id"],
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": f"[RAEN dispute_letter] Formal notice to {args['recipient']} citing {args['statutory_basis']}: {args['requested_remedy']}.",
                    }
                ]
            },
        }

    set_default_client(RaenMcpGatewayClient(api_key="demo-raen-key", transport=demo_transport))
    analysis = contract_analyze(
        contract_text="Section 9: Customer shall indemnify Vendor without cap. Section 12: Renews automatically for 24 months unless notice given 60 days prior.",
        jurisdiction="US-NY",
    )
    letter = dispute_letter(
        recipient="Acme Cloud Services Billing Dept",
        claim_summary=analysis,
        statutory_basis="NY GBL § 5-903 (Automatic Renewal Notice Requirement)",
        requested_remedy="Cancel unauthorized auto-renewal and refund invoice #INV-2026-109",
    )
    return {"contract_analysis": analysis, "dispute_letter": letter}


if __name__ == "__main__":
    print(json.dumps(run_demo_crew_flow(), indent=2))
