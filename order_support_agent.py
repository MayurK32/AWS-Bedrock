from pydantic import BaseModel
from strands import Agent, AgentSkills, tool
from strands.tools.mcp import MCPClient
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from support_hooks import ToolLogHook, tool_logs

app = FastAPI()

class promptRequest(BaseModel):
    prompt: str
    session_id: str

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

# In-memory conversation history keyed by session ID.
sessions: dict[str, list] = {}

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


skills_plugin = AgentSkills(skills="./skills/")

SYSTEM_PROMPT = """You are an order-support assistant for an e-commerce platform.
You help customers check order status, manage support tickets, and resolve issues.
Only confirm actions after the tool reports success.
Never invent statuses, ticket numbers, delivery dates, or response deadlines.
These tools update demo data — never claim a real support team has been notified."""


@app.get("/tools/logs/{session_id}")
async def get_tool_logs(session_id: str):
    return tool_logs.get(session_id, [])


@app.post("/stream")
async def stream_responses(request: promptRequest):
    async def generate():
        with remoteClient:
            mcpTools = remoteClient.list_tools_sync()

            history = sessions.get(request.session_id, [])

            agent = Agent(
                model="zai.glm-4.7",
                tools=[checkOrderStatus, *mcpTools],
                system_prompt=SYSTEM_PROMPT,
                plugins=[skills_plugin],
                callback_handler=None,
                hooks=[ToolLogHook(session_id=request.session_id)],
                messages=history,
            )

            try:
                async for event in agent.stream_async(request.prompt):
                    if "data" in event:
                        yield event["data"]
            except Exception as e:
                yield f"\n[Error: {e}]"
            finally:
                sessions[request.session_id] = agent.messages

    return StreamingResponse(generate(), media_type="text/plain")
