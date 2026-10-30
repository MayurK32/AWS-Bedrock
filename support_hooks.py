from strands.hooks import HookProvider, HookRegistry, BeforeToolCallEvent

class TicketClosureHook(HookProvider):

    def register_hooks(self, registry: HookRegistry)-> None:
        registry.add_callback(BeforeToolCallEvent, self.check_close)

    def check_close(self, event:BeforeToolCallEvent)-> None:
        if event.tool_use['name'] != "ticket_close":
            return

        approval = event.interrupt(
            "ticket_close_approval",
            reason={"path": event.tool_use["input"]["path"]}
        )

        if approval.lower() != "y":
            event.cancel_tool("User rejected ticket closure.")