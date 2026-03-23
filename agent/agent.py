# agent/agent.py
# ReAct loop — Reason, Act, Observe, Repeat
#
# Changes from original:
#   1. Injects pending tasks into the system prompt so the LLM knows what's queued
#   2. Handles "schedule_task" tool calls — saves future tasks to task_store
#   3. Handles "cancel_task" tool calls
#   4. Handles "list_tasks" tool calls

import json
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from providers.index import get_provider
from agent.memory import get_history, add_message
from agent.toolRouter import TOOL_DEFINITIONS, execute_tool
from agent.task_store import (
    add_task,
    cancel_task,
    get_pending_tasks,
    format_pending_for_prompt,
)
from config.settings import settings

SYSTEM_PROMPT = """You are AgentX — a personal AI assistant that controls a user's Android phone.

You can:
- Send, read, search Gmail emails
- Create and check Google Calendar events
- Set alarms on the user's phone
- Look up Google Contacts
- Search the web
- Schedule any tool to run in the future using schedule_task
- Cancel scheduled tasks using cancel_task
- List pending scheduled tasks using list_tasks

Current date/time (UTC): {datetime}

{pending_tasks_block}

RULES:
1. FUTURE vs NOW — this is the most important rule:
   - "in X minutes/hours", "after X minutes", "remind me in X" → use schedule_task with delay_seconds
   - "at 9pm", "tomorrow morning", "on Friday" → use schedule_task with execute_at_utc
   - "now", "immediately", "set an alarm for 7am" (no delay) → use set_alarm directly
   "remind me to drink water in 2 minutes" MUST use schedule_task with tool_name="set_alarm", NOT send_email.

2. Reminders are ALWAYS alarms, never emails. "Remind me to X" = schedule_task with tool_name="set_alarm".
   Only use send_email when the user explicitly says "email" or "send a message to someone".

3. For alarms — convert natural language to 24h format. "9 PM" = hour=21, minute=0.
   set_alarm args must be: hour (int), minute (int), label (string).

4. Be concise — this is a chat interface.

5. Reply in the same language the user used (Hindi, Tamil, English etc.)

6. After executing, confirm what you did in plain language.

7. If you need a contact's email, use lookup_contact first.

8. Never re-schedule a task that is already in PENDING TASKS above.

9. If the message starts with [Completed task: ...] lines, always acknowledge those completions
   naturally in your reply before answering the user's actual question.
"""

SCHEDULE_TOOL = {
    "type": "function",
    "function": {
        "name": "schedule_task",
        "description": (
            "Schedule any tool to run in the future. "
            "Use this whenever the user says 'in X minutes/hours', 'remind me', "
            "'after X minutes', or 'do this later'. "
            "Do NOT call the underlying tool directly for future tasks — use this instead. "
            "For reminders, set tool_name='set_alarm' with hour, minute, label as tool_args."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "tool_name": {
                    "type": "string",
                    "description": "The tool to call when the time comes (e.g. 'set_alarm', 'send_email')"
                },
                "tool_args": {
                    "type": "object",
                    "description": (
                        "ONLY the arguments for the target tool. "
                        "Do not include 'description' here — that is a separate top-level field. "
                        "For set_alarm: {hour: int, minute: int, label: string}. "
                        "For send_email: {to: string, subject: string, body: string}."
                    )
                },
                "delay_seconds": {
                    "type": "integer",
                    "description": "How many seconds from now to execute. Use for relative times like 'in 5 minutes' (=300), 'in 1 hour' (=3600)."
                },
                "execute_at_utc": {
                    "type": "string",
                    "description": (
                        "Absolute UTC datetime to execute, ISO format (YYYY-MM-DDTHH:MM:SS). "
                        "Use for absolute times like 'at 9 PM' or 'tomorrow morning'. "
                        "Provide either delay_seconds OR execute_at_utc, not both."
                    )
                },
                "description": {
                    "type": "string",
                    "description": (
                        "Human-readable label shown to the user. REQUIRED. "
                        "Examples: 'Drink water reminder', 'Send leave email to professor'. "
                        "Never use the tool name as the description."
                    )
                },
            },
            "required": ["tool_name", "tool_args", "description"]
        }
    }
}

CANCEL_TOOL = {
    "type": "function",
    "function": {
        "name": "cancel_task",
        "description": "Cancel a pending scheduled task by its task_id.",
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "The 8-character task ID shown in the pending tasks list"
                }
            },
            "required": ["task_id"]
        }
    }
}

LIST_TASKS_TOOL = {
    "type": "function",
    "function": {
        "name": "list_tasks",
        "description": "List all pending scheduled tasks for this session.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
}

ALL_TOOLS = TOOL_DEFINITIONS + [SCHEDULE_TOOL, CANCEL_TOOL, LIST_TASKS_TOOL]


async def run_agent(
    user_message: str,
    session_id: str,
    provider: str,
    api_key: str,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    google_token: Optional[dict] = None,
) -> Dict[str, Any]:

    now_utc = datetime.utcnow()
    now_str = now_utc.strftime("%A, %B %d %Y at %H:%M UTC")

    llm = get_provider(provider=provider, api_key=api_key, model=model, base_url=base_url)

    history = get_history(session_id)
    add_message(session_id, "user", user_message)
    messages = history + [{"role": "user", "content": user_message}]

    # Inject pending tasks into system prompt so LLM is aware of them
    pending_block = format_pending_for_prompt(session_id) or ""

    system = SYSTEM_PROMPT.format(
        datetime=now_str,
        pending_tasks_block=pending_block,
    )

    actions_taken = []
    alarm_data = None

    for iteration in range(settings.max_iterations):
        response = await llm.chat_with_tools(
            messages=messages,
            tools=ALL_TOOLS,
            system_prompt=system,
        )

        # Process ALL tool calls, not just the first one
        tool_calls = response.get("tool_calls") or []

        if not tool_calls:
            # No tool call — final reply
            final_reply = response.get("content", "Done!")
            add_message(session_id, "assistant", final_reply)
            return {
                "reply": final_reply,
                "actions_taken": actions_taken,
                "alarm_data": alarm_data,
                "requires_confirmation": False,
                "iterations": iteration + 1,
            }

        # Append assistant turn with all tool calls
        messages.append({
            "role": "assistant",
            "content": response.get("content") or "",
            "tool_calls": tool_calls,
        })

        # Execute each tool call and collect results
        for tool_call in tool_calls:
            tool_name = tool_call.function.name
            tool_args = json.loads(tool_call.function.arguments)

            # ── schedule_task ──────────────────────────────────────────────
            if tool_name == "schedule_task":
                tool_result = _handle_schedule_task(
                    tool_args, session_id, google_token, now_utc
                )

            # ── cancel_task ────────────────────────────────────────────────
            elif tool_name == "cancel_task":
                cancelled = cancel_task(tool_args["task_id"], session_id)
                tool_result = (
                    f"Task [{tool_args['task_id']}] cancelled."
                    if cancelled
                    else f"Task [{tool_args['task_id']}] not found or already completed."
                )

            # ── list_tasks ─────────────────────────────────────────────────
            elif tool_name == "list_tasks":
                pending = get_pending_tasks(session_id)
                if not pending:
                    tool_result = "No pending tasks."
                else:
                    lines = [f"  [{t['task_id']}] {t['description']}" for t in pending]
                    tool_result = "Pending tasks:\n" + "\n".join(lines)

            # ── set_alarm (immediate — React Native handles it) ────────────
            elif tool_name == "set_alarm":
                alarm_data = tool_args
                tool_result = (
                    f"Alarm set for {tool_args['hour']:02d}:{tool_args['minute']:02d}"
                    + (f" — {tool_args.get('label', '')}" if tool_args.get("label") else "")
                )

            # ── all other tools ────────────────────────────────────────────
            else:
                tool_result = await _safe_execute(tool_name, tool_args, google_token)

            actions_taken.append({
                "tool": tool_name,
                "args": tool_args,
                "result": tool_result,
            })

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": tool_result,
            })

    # Max iterations hit
    return {
        "reply": "I've completed the actions: " + ", ".join(a["tool"] for a in actions_taken),
        "actions_taken": actions_taken,
        "alarm_data": alarm_data,
        "requires_confirmation": False,
        "iterations": settings.max_iterations,
    }


def _handle_schedule_task(
    args: dict,
    session_id: str,
    google_token: Optional[dict],
    now_utc: datetime,
) -> str:
    """Parse schedule_task args, validate, save to task_store, return confirmation string."""
    tool_name   = args.get("tool_name")
    tool_args   = args.get("tool_args", {})
    description = args.get("description", tool_name)

    # Resolve execute_at
    if args.get("delay_seconds") is not None:
        execute_at = now_utc + timedelta(seconds=int(args["delay_seconds"]))
    elif args.get("execute_at_utc"):
        try:
            execute_at = datetime.fromisoformat(args["execute_at_utc"])
        except ValueError:
            return f"Error: invalid execute_at_utc format '{args['execute_at_utc']}'. Use YYYY-MM-DDTHH:MM:SS."
    else:
        return "Error: provide either delay_seconds or execute_at_utc."

    if execute_at <= now_utc:
        return "Error: scheduled time is in the past."

    task_id = add_task(
        session_id=session_id,
        tool_name=tool_name,
        tool_args=tool_args,
        execute_at=execute_at,
        description=description,
        google_token=google_token,
    )

    # Human readable confirmation
    delta = execute_at - now_utc
    total_s = int(delta.total_seconds())
    if total_s < 60:
        when = f"in {total_s}s"
    elif total_s < 3600:
        when = f"in {total_s // 60} min"
    else:
        h, m = total_s // 3600, (total_s % 3600) // 60
        when = f"in {h}h {m}min"

    return f"Task [{task_id}] scheduled: '{description}' — will run {when}."


async def _safe_execute(tool_name: str, tool_args: dict, google_token) -> str:
    """Wrap execute_tool with a structured error so the LLM gets clean feedback."""
    try:
        return await execute_tool(tool_name, tool_args, google_token)
    except Exception as e:
        return f"Tool '{tool_name}' encountered an error: {str(e)}"