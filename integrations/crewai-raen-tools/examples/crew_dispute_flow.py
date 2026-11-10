"""Example CrewAI crew making one real RAEN MCP gateway call (bounty 3 demo).

Run:
    export RAEN_MCP_KEY=<your 30-day RAEN dev key>
    export OPENAI_API_KEY=<any model key CrewAI supports>
    python examples/crew_dispute_flow.py

The crew's single task calls the `raen_dispute_letter` tool, which spends $0.75
USDC on Base through the gateway and returns a drafted FCRA dispute letter.
"""

import os
import sys

from crewai import Agent, Crew, Process, Task

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from raen_crewai_tools import raen_contract_analysis, raen_dispute_letter


def main():
    if not os.environ.get("RAEN_MCP_KEY"):
        sys.exit("Set RAEN_MCP_KEY to your RAEN MCP gateway dev key first.")

    analyst = Agent(
        role="Consumer Rights Analyst",
        goal="Turn a consumer complaint into a ready-to-send dispute package.",
        backstory="Detail-oriented analyst who drafts CROA-compliant dispute letters "
                  "and reviews contracts for one-sided clauses using paid RAEN tools.",
        tools=[raen_dispute_letter, raen_contract_analysis],
    )

    task = Task(
        description="The consumer disputes an account with 'Acme Collections LLC' on the "
                    "grounds that the debt is not theirs and was reported inaccurately. "
                    "Call the raen_dispute_letter tool once with creditor='Acme Collections LLC' "
                    "and reason='Debt is not mine / inaccurate reporting', then present the "
                    "letter_body from the result.",
        expected_output="The drafted dispute letter body text plus the on-chain certificate signature.",
        agent=analyst,
    )

    crew = Crew(agents=[analyst], tasks=[task], process=Process.sequential)
    result = crew.kickoff()
    print(result)


if __name__ == "__main__":
    main()
