from pydantic import BaseModel
from strands import Agent, tool, Hookprovider
from strands.tools.mcp import MCPClient
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

app = FastAPI()

class promptRequest(BaseModel):
    prompt: str

class SupportTicket(BaseModel):
    ticketNo: int
    productName: str
    issue: str
    escalationlevel: str = "normal"
    status: str = "open"


orderStatusDict = {
    "playgym": "pending",
    "cotton diapers": "delivered",
    "tops": "return-inprogress",
    "sweaters": "not-shipped",
}

# Demo storage: tickets disappear when the script stops.
tickets: dict[int, SupportTicket] = {}

remoteClient = MCPClient(
    url="http://127.0.0.1:8756/mcp",
    tool_filters={
        "rejected" : ["demo_weather", "demo_currency_convert", "demo_inventory_lookup", "demo_shipping_quote"]
    }
)

@tool
def checkOrderStatus(productName: str) -> dict:
    """Get an order's status using a product name or keyword.

    Args:
        productName: Product name or keyword, such as diapers.
    """
    query = productName.strip().casefold()
    if not query:
        return {"error": "Product name is required"}

    matches = (
        [query] if query in orderStatusDict
        else [name for name in orderStatusDict if query in name.casefold()]
    )
    if len(matches) == 1:
        name = matches[0]
        return {"product": name, "status": orderStatusDict[name]}
    if len(matches) > 1:
        return {"error": "Multiple products matched", "products": matches}
    return {"error": "Order not found"}

def see_tickets() -> None:
    if not tickets:
        print("No support tickets found.")
    for ticket in tickets.values():
        print(
            f"\nTicket #{ticket.ticketNo}\n"
            f"Product: {ticket.productName}\n"
            f"Issue: {ticket.issue}\n"
            f"Escalation level: {ticket.escalationlevel.title()}\n"
            f"Status: {ticket.status.title()}\n"
            f"{'-' * 40}"
        )


SYSTEM_PROMPT = """
You are an order-support assistant.
Use checkOrderStatus for order status. If multiple products match, ask which one.
Use the canonical product name returned by that tool for support tickets.
Use ticketRaiser when the user asks to raise a ticket. Ask for the product and
issue if unknown; reuse those details from this conversation when available.
Use normal priority unless the user requests high priority.
For an existing ticket's status, use getTicketStatus; do not call ticketRaiser
just to check status because that tool can create a ticket.
If a customer reports no support response for two or more days after raising
an existing complaint, call escalateTicket without asking for confirmation.
Also call escalateTicket when the user explicitly requests escalation.
Use the existing ticket number from the conversation. Ask if it is unknown
or ambiguous. Never create a new ticket merely to escalate an existing one.
Only confirm creation or escalation after the tool reports success.
Report the ticket number, current status, and escalation level from tool results.
Never invent statuses, ticket numbers, delivery dates, response deadlines, or
claim that a real support team has been notified. These tools update demo data.
If user confirms that isssue has been resolved, acknowledge them with ticket details
and get theier consent to close the ticket and update the status of ticket and acknowledge back
Keep your tone supportive and informative
"""


@app.post("/stream")
async def stream_responses(request: promptRequest):
    async def generate():
        with remoteClient:
            mcpTools = remoteClient.list_tools_sync()

            agent = Agent(
                model="zai.glm-4.7",
                tools=[checkOrderStatus, *mcpTools],
                system_prompt=SYSTEM_PROMPT,
                callback_handler=None,
            )

            async for event in agent.stream_async(request.prompt):
                if "data" in event:
                    yield event["data"]

    return StreamingResponse(generate(), media_type="text/plain")
