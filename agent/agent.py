# agent/agent.py
# ReAct loop — Reason, Act, Observe, Repeat

import json
from typing import Optional, Dict, Any
from datetime import datetime
from providers.index import get_provider
from agent.memory import get_history, add_message
from agent.toolRouter import TOOL_DEFINITIONS, execute_tool
from config.settings import settings

SYSTEM_PROMPT = """You are PhoneAgent — a personal AI assistant that controls a user's Android phone.

You can:
- Send, read, search Gmail emails
- Create and check Google Calendar events
- Set alarms on the user's phone
- Look up Google Contacts
- Search the web

Current date/time: {datetime}

RULES:
1. For alarms — convert natural language to 24h format. "9 PM" = hour=21, minute=0.
2. Be concise — this is a chat interface.
3. Reply in the same language the user used (Hindi, Tamil, English etc.)
4. After executing, confirm what you did in plain language.
5. If you need a contact's email, use lookup_contact first.
"""

async def run_agent(
    user_message: str,
    session_id: str,
    provider: str,
    api_key: str,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    google_token: Optional[str] = None,
) -> Dict[str, Any]:

    now = datetime.now().strftime("%A, %B %d %Y at %I:%M %p")
    llm = get_provider(provider=provider, api_key=api_key, model=model, base_url=base_url)

    history = get_history(session_id)
    add_message(session_id, "user", user_message)
    messages = history + [{"role": "user", "content": user_message}]

    actions_taken = []
    alarm_data = None

    for iteration in range(settings.max_iterations):
        response = await llm.chat_with_tools(
            messages=messages,
            tools=TOOL_DEFINITIONS,
            system_prompt=SYSTEM_PROMPT.format(datetime=now),
        )

        if response.get("tool_calls"):
            tool_call = response["tool_calls"][0]
            tool_name = tool_call.function.name
            tool_args = json.loads(tool_call.function.arguments)

            # Alarm is handled by React Native — backend just validates
            if tool_name == "set_alarm":
                alarm_data = tool_args
                tool_result = f"Alarm set for {tool_args['hour']:02d}:{tool_args['minute']:02d}"
            else:
                tool_result = await execute_tool(tool_name, tool_args, google_token)

            actions_taken.append({"tool": tool_name, "args": tool_args, "result": tool_result})

            messages.append({
                "role": "assistant",
                "content": response.get("content") or "",
                "tool_calls": response["tool_calls"]
            })
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": tool_result
            })

        else:
            final_reply = response.get("content", "Done!")
            add_message(session_id, "assistant", final_reply)
            return {
                "reply": final_reply,
                "actions_taken": actions_taken,
                "alarm_data": alarm_data,
                "requires_confirmation": False,
                "iterations": iteration + 1
            }

    return {
        "reply": "Task completed: " + ", ".join([a["tool"] for a in actions_taken]),
        "actions_taken": actions_taken,
        "alarm_data": alarm_data,
        "requires_confirmation": False,
        "iterations": settings.max_iterations
    }