from datetime import datetime

from strands.hooks import HookProvider, HookRegistry, BeforeToolCallEvent, AfterToolCallEvent

# Per-session tool usage logs.
tool_logs: dict[str, list] = {}


class ToolLogHook(HookProvider):

    def __init__(self, session_id: str):
        self.session_id = session_id

    def register_hooks(self, registry: HookRegistry) -> None:
        registry.add_callback(BeforeToolCallEvent, self.on_before_tool)
        registry.add_callback(AfterToolCallEvent, self.on_after_tool)

    def on_before_tool(self, event: BeforeToolCallEvent) -> None:
        entry = {
            "tool": event.tool_use["name"],
            "input": event.tool_use.get("input", {}),
            "timestamp": datetime.now().isoformat(),
            "result": None,
        }
        logs = tool_logs.setdefault(self.session_id, [])
        logs.append(entry)
        print(f"[HOOK] Tool called: {entry['tool']} | Input: {entry['input']}")

    def on_after_tool(self, event: AfterToolCallEvent) -> None:
        logs = tool_logs.get(self.session_id, [])
        if not logs:
            return

        last = logs[-1]
        if last["tool"] == event.tool_use["name"]:
            last["result"] = event.result
            print(f"[HOOK] Tool done: {last['tool']} | Result: {event.result}")
