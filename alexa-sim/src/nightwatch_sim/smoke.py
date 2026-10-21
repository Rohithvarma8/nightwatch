"""make sim-smoke: run the demo turns against the live MCP server and print what happened.

Real side effects: the confirmed turns notify the contact and start a CodeDeploy rollback.
"""

import argparse
import sys
import uuid

from nightwatch_sim.engine import Engine
from nightwatch_sim.settings import Settings

DEMO_TURNS = [
    "what's going on?",
    "why do you think it's the deploy?",
    "acknowledge the page and tell my roommate about the fire warning",
    "yes",
    "roll it back",
    "yes",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("turns", nargs="*", help="override the demo turns")
    args = parser.parse_args()
    settings = Settings.from_env()
    engine = Engine(settings)
    session = uuid.uuid4().hex
    failed = False
    print(f"MCP {settings.mcp_url}")
    print(f"model {settings.primary_model} (fallback {settings.fallback_model})")
    try:
        for i, text in enumerate(args.turns or DEMO_TURNS, 1):
            turn = engine.turn(session, text)
            tool_ms = sum(c.latency_ms for c in turn.tools)
            print(f"\n[{i}] you:   {text}")
            print(f"    alexa: {turn.reply}")
            for c in turn.tools:
                print(f"    tool   {c.name} {c.arguments} → {c.status}, {c.latency_ms} ms")
            if not turn.tools:
                print("    tool   (none)")
            card = turn.card
            if card:
                print(f"    card   {card['uri']}")
            print(
                f"    time   {turn.total_ms} ms total · {tool_ms} ms MCP · "
                f"{turn.total_ms - tool_ms} ms model ({turn.model})"
            )
            if turn.error:
                failed = True
                print(f"    ERROR  {turn.error}")
    finally:
        engine.close()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
