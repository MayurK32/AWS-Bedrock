"""Insert fictional support tickets through an already running MCP server.

Run: python seed_tickets.py
Or:  python seed_tickets.py --url http://127.0.0.1:8756/mcp
Uses FastMCP, which is already required by the ticket server. No model calls.
Existing active exact-match tickets are reused; existing data is never deleted.
"""
import argparse
import asyncio
import sys

from fastmcp import Client


DUMMY_TICKETS = [
    {"product_name": "cotton diapers", "issue": "Marked delivered but not received", "priority": "normal"},
    {"product_name": "playgym", "issue": "Some parts are missing", "priority": "high"},
    {"product_name": "tops", "issue": "Return pickup has not been arranged", "priority": "normal"},
    {"product_name": "sweaters", "issue": "Order has not shipped", "priority": "normal"},
    {"product_name": "baby blanket", "issue": "Wrong product delivered; replacement required urgently", "priority": "urgent"},
]


async def seed(url: str) -> list[dict]:
    results = []
    async with Client(url) as client:
        for record in DUMMY_TICKETS:
            result = await client.call_tool("ticket_raise", record)
            payload = result.data
            ticket = payload["ticket"]
            print(
                f"{payload['action']}: Ticket #{ticket['ticket_no']} | "
                f"{ticket['product_name']} | Status: {ticket['status']} | "
                f"Priority: {ticket['priority']}"
            )
            results.append(payload)
    created = sum(item["action"] == "created" for item in results)
    print(f"\nDone: {created} created, {len(results) - created} existing tickets reused.")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8756/mcp")
    args = parser.parse_args()
    try:
        asyncio.run(seed(args.url))
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(f"Seed stopped: {exc}", file=sys.stderr)
        print("Keep the MCP server running and check --url. Earlier inserts may have succeeded; rerun to reuse them.", file=sys.stderr)
        raise SystemExit(1)
