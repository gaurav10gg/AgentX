# agent/agent.py
# ReAct loop â€” Reason, Act, Observe, Repeat
#
# Changes from original:
#   1. Injects pending tasks into the system prompt so the LLM knows what's queued
#   2. Handles "schedule_task" tool calls â€” saves future tasks to task_store
#   3. Handles "cancel_task" tool calls
#   4. Handles "list_tasks" tool calls
#   5. [FIX] _handle_schedule_task now structurally validates args before saving,
#      so LLM mistakes (e.g. schedule send_email with no "to") are caught and
#      returned as errors rather than saved as broken tasks.

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

# ---------------------------------------------------------------------------
# Per-tool required fields and validation rules.
# Any tool scheduled via schedule_task is checked against this table before
# being saved. This is the structural enforcement layer â€” the LLM's instruction
# following is unreliable, so we validate here unconditionally.
# ---------------------------------------------------------------------------
SCHEDULED_TOOL_RULES: Dict[str, Dict] = {
    "set_alarm": {
        "required": ["hour", "minute"],
        "types": {"hour": int, "minute": int},
        "ranges": {"hour": (0, 23), "minute": (0, 59)},
    },
    "send_email": {
        "required": ["to", "subject", "body"],
        # "to" must be a non-empty string â€” the most common LLM mistake
        "non_empty": ["to", "subject"],
    },
    "create_event": {
        "required": ["title", "date", "time"],
        "non_empty": ["title", "date", "time"],
    },
    "web_search": {
        "required": ["query"],
        "non_empty": ["query"],
    },
    # Other tools have no extra constraints beyond being known tool names
}

# Tools that are valid to schedule at all. If the LLM tries to schedule
# something nonsensical (e.g. schedule_task with tool_name="schedule_task"),
# reject it immediately.
SCHEDULABLE_TOOLS = {t["function"]["name"] for t in TOOL_DEFINITIONS}


# ---------------------------------------------------------------------------
# Reminder-intent keywords â€” if the user message looks like a reminder and
# the LLM tries to schedule send_email, we catch it here and correct it.
# This is a last-resort guard; the system prompt is the first line of defense.
# ---------------------------------------------------------------------------

IST_OFFSET = timedelta(hours=5, minutes=30)
REMINDER_KEYWORDS = {
    "remind",
    "reminder",
    "alert",
    "alarm",
    "ping",
    "wake",
    "water",
}


def _looks_like_reminder(description: str) -> bool:
    """Return True if the task description sounds like a reminder/alarm."""
    words = description.lower().split()
    return bool(REMINDER_KEYWORDS & set(words))


SYSTEM_PROMPT = """You are AgentX â€” a personal AI assistant that controls a user's Android phone.

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
User timezone: IST (UTC+5:30). When the user says "9 PM" or "tomorrow morning",
convert to UTC by subtracting 5 hours 30 minutes before passing to execute_at_utc.
Example: user says "9 PM IST" â†’ execute_at_utc = today's date + "15:30:00" (UTC).

{pending_tasks_block}

RULES â€” read every rule before deciding which tool to call:

1. FUTURE vs NOW â€” most important rule:
   - "in X minutes/hours", "after X", "remind me in X" â†’ schedule_task with delay_seconds
   - "at 9pm", "tomorrow morning", "on Friday"         â†’ schedule_task with execute_at_utc (converted to UTC)
   - "now", "immediately", no delay mentioned           â†’ call the tool directly

2. REMINDERS ARE ALWAYS ALARMS â€” never emails.
   "Remind me to X", "alert me", "ping me", "wake me up" â†’ schedule_task with tool_name="set_alarm".
   NEVER use send_email for a reminder. send_email is ONLY for explicitly sending a message to another person.
   If you find yourself writing tool_name="send_email" for a reminder, STOP and use tool_name="set_alarm" instead.

3. set_alarm args must be integers: {{ "hour": <int 0-23>, "minute": <int 0-59>, "label": "<string>" }}.
   Do NOT pass strings like "21" â€” pass the integer 21.

4. schedule_task "description" field is REQUIRED and must be human-readable.
   Good: "Drink water reminder"   Bad: "send_email" or "set_alarm"

5. For absolute times, always provide execute_at_utc in ISO format YYYY-MM-DDTHH:MM:SS (UTC).
   For relative times, always provide delay_seconds as a plain integer.
   Never provide both. Never omit both.

6. If you need a contact's email, use lookup_contact first before calling send_email.

7. Never re-schedule a task already listed in PENDING TASKS above.

8. Be concise â€” this is a chat interface. Confirm what you did in plain language.

9. Reply in the same language the user used (Hindi, Tamil, English, etc.)

10. If the message starts with [Completed task: ...] lines, acknowledge those completions
    naturally before answering the user's actual question.
"""

SCHEDULE_TOOL = {
    "type": "function",
    "function": {
        "name": "schedule_task",
        "description": (
            "Schedule any tool to run in the future. "
            "Use whenever the user says 'in X minutes/hours', 'remind me', "
            "'after X', or 'do this later'. "
            "IMPORTANT: for reminders/alerts, always set tool_name='set_alarm' â€” "
            "NEVER tool_name='send_email' for a reminder. "
            "Do NOT call the underlying tool directly for future tasks."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "tool_name": {
                    "type": "string",
                    "description": (
                        "Tool to call when the time comes. "
                        "For reminders/alerts: 'set_alarm'. "
                        "For future emails to other people: 'send_email'. "
                        "For future calendar events: 'create_event'."
                    ),
                },
                "tool_args": {
                    "type": "object",
                    "description": (
                        "Arguments for the target tool ONLY â€” no 'description' here. "
                        "set_alarm:   {\"hour\": <int>, \"minute\": <int>, \"label\": <str>}. "
                        "send_email:  {\"to\": <non-empty email>, \"subject\": <str>, \"body\": <str>}. "
                        "create_event:{\"title\": <str>, \"date\": <YYYY-MM-DD>, \"time\": <HH:MM>}."
                    ),
                },
                "delay_seconds": {
                    "type": "integer",
                    "description": "Seconds from now. Use for 'in 5 minutes' (=300), 'in 1 hour' (=3600).",
                },
                "execute_at_utc": {
                    "type": "string",
                    "description": (
                        "Absolute UTC datetime ISO format YYYY-MM-DDTHH:MM:SS. "
                        "Convert IST to UTC by subtracting 5h30m. "
                        "Use for 'at 9 PM', 'tomorrow morning'. "
                        "Provide EITHER delay_seconds OR execute_at_utc, not both."
                    ),
                },
                "description": {
                    "type": "string",
                    "description": (
                        "REQUIRED. Human-readable label shown to the user. "
                        "Examples: 'Drink water reminder', 'Send leave email to professor'. "
                        "Never use the tool name as the description."
                    ),
                },
            },
            "required": ["tool_name", "tool_args", "description"],
        },
    },
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
                    "description": "The 8-character task ID shown in the pending tasks list",
                }
            },
            "required": ["task_id"],
        },
    },
}

LIST_TASKS_TOOL = {
    "type": "function",
    "function": {
        "name": "list_tasks",
        "description": "List all pending scheduled tasks for this session.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}

ALL_TOOLS = TOOL_DEFINITIONS + [SCHEDULE_TOOL, CANCEL_TOOL, LIST_TASKS_TOOL]


async def run_agent(
    user_message: str,
    session_id: str,
    user_id: str,
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

        tool_calls = response.get("tool_calls") or []

        if not tool_calls:
            final_reply = response.get("content", "Done!")
            add_message(session_id, "assistant", final_reply)
            return {
                "reply": final_reply,
                "actions_taken": actions_taken,
                "alarm_data": alarm_data,
                "requires_confirmation": False,
                "iterations": iteration + 1,
            }

        messages.append({
            "role": "assistant",
            "content": response.get("content") or "",
            "tool_calls": tool_calls,
        })

        for tool_call in tool_calls:
            tool_name = tool_call.function.name
            tool_args = json.loads(tool_call.function.arguments)

            # â”€â”€ schedule_task â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            if tool_name == "schedule_task":
                tool_result = _handle_schedule_task(
                    tool_args, session_id, user_id, google_token, now_utc
                )

            # â”€â”€ cancel_task â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            elif tool_name == "cancel_task":
                cancelled = cancel_task(tool_args["task_id"], session_id)
                tool_result = (
                    f"Task [{tool_args['task_id']}] cancelled."
                    if cancelled
                    else f"Task [{tool_args['task_id']}] not found or already completed."
                )

            # â”€â”€ list_tasks â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            elif tool_name == "list_tasks":
                pending = get_pending_tasks(session_id)
                if not pending:
                    tool_result = "No pending tasks."
                else:
                    lines = [f"  [{t['task_id']}] {t['description']}" for t in pending]
                    tool_result = "Pending tasks:\n" + "\n".join(lines)

            # â”€â”€ set_alarm (immediate) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            elif tool_name == "set_alarm":
                alarm_data = tool_args
                tool_result = (
                    f"Alarm set for {tool_args['hour']:02d}:{tool_args['minute']:02d}"
                    + (f" â€” {tool_args.get('label', '')}" if tool_args.get("label") else "")
                )

            # â”€â”€ all other tools â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

    return {
        "reply": "I've completed the actions: " + ", ".join(a["tool"] for a in actions_taken),
        "actions_taken": actions_taken,
        "alarm_data": alarm_data,
        "requires_confirmation": False,
        "iterations": settings.max_iterations,
    }


# ---------------------------------------------------------------------------
# Scheduling validation â€” the structural enforcement layer.
# The LLM is asked nicely in the system prompt. This function enforces it hard.
# ---------------------------------------------------------------------------

def _validate_scheduled_tool(tool_name: str, tool_args: dict, description: str) -> Optional[str]:
    """
    Validate a scheduled tool call before it is saved.

    Returns an error string if invalid, or None if everything looks good.

    Checks performed:
      1. tool_name must be a known, schedulable tool.
      2. Reminder-intent + send_email mismatch â†’ redirect to set_alarm.
      3. Per-tool required fields must be present.
      4. Per-tool non-empty string fields must not be blank.
      5. Per-tool integer fields must be actual ints within valid ranges.
    """

    # 1. Must be a known tool
    if tool_name not in SCHEDULABLE_TOOLS:
        return (
            f"Error: '{tool_name}' is not a schedulable tool. "
            f"Valid options: {', '.join(sorted(SCHEDULABLE_TOOLS))}."
        )

    # 2. Reminder-intent guard â€” catch the exact bug that caused the water reminder failure.
    #    If the description sounds like a reminder but the tool is send_email, reject it
    #    with a clear corrective message so the LLM retries with set_alarm.
    if tool_name == "send_email" and _looks_like_reminder(description):
        return (
            "Error: reminders must use tool_name='set_alarm', not 'send_email'. "
            "Retry this schedule_task call with tool_name='set_alarm' and "
            "tool_args={\"hour\": <int>, \"minute\": <int>, \"label\": \"<reminder text>\"}."
        )

    # 3 & 4 & 5. Per-tool field rules
    rules = SCHEDULED_TOOL_RULES.get(tool_name)
    if rules is None:
        return None  # No extra rules for this tool â€” allow it

    # 3. Required fields must be present (key exists)
    for field in rules.get("required", []):
        if field not in tool_args:
            return (
                f"Error: '{tool_name}' requires field '{field}' but it was not provided. "
                f"Required fields: {rules['required']}."
            )

    # 4. Non-empty string fields must not be blank / None
    for field in rules.get("non_empty", []):
        value = tool_args.get(field)
        if not value or (isinstance(value, str) and not value.strip()):
            return (
                f"Error: '{tool_name}' field '{field}' must not be empty. "
                + (
                    "For send_email, 'to' must be a real recipient email address. "
                    "Use lookup_contact first if you don't know the address."
                    if field == "to"
                    else f"Provide a non-empty value for '{field}'."
                )
            )

    # 5. Integer type and range checks
    for field, expected_type in rules.get("types", {}).items():
        value = tool_args.get(field)
        if value is None:
            continue  # already caught by required check above
        if not isinstance(value, expected_type):
            # Try to coerce â€” LLMs sometimes pass "21" instead of 21
            try:
                coerced = expected_type(value)
                tool_args[field] = coerced  # mutate in place so save uses the clean value
                value = coerced
            except (ValueError, TypeError):
                return (
                    f"Error: '{tool_name}' field '{field}' must be an integer, "
                    f"got {type(value).__name__} ({value!r})."
                )
        # Range check
        if field in rules.get("ranges", {}):
            lo, hi = rules["ranges"][field]
            if not (lo <= value <= hi):
                return (
                    f"Error: '{tool_name}' field '{field}' must be between {lo} and {hi}, "
                    f"got {value}."
                )

    return None  # all checks passed


def _handle_schedule_task(
    args: dict,
    session_id: str,
    user_id: str,
    google_token: Optional[dict],
    now_utc: datetime,
) -> str:
    """Parse schedule_task args, validate, save to task_store, return confirmation string."""
    tool_name = args.get("tool_name", "")
    tool_args = args.get("tool_args", {})
    description = args.get("description", "").strip() or tool_name

    if not args.get("description", "").strip():
        return (
            "Error: 'description' is required and must be a human-readable label. "
            "Example: 'Drink water reminder'. Retry with a non-empty description."
        )

    if not isinstance(tool_args, dict):
        return "Error: 'tool_args' must be an object."

    # Providers occasionally place scheduling keys inside tool_args.
    delay_seconds = args.get("delay_seconds")
    execute_at_utc = args.get("execute_at_utc")
    if delay_seconds is None and tool_args.get("delay_seconds") is not None:
        delay_seconds = tool_args.pop("delay_seconds")
    if execute_at_utc is None and tool_args.get("execute_at_utc"):
        execute_at_utc = tool_args.pop("execute_at_utc")

    if delay_seconds is not None and execute_at_utc is not None:
        return "Error: provide either delay_seconds OR execute_at_utc, not both."

    if delay_seconds is not None:
        try:
            delay = int(delay_seconds)
        except (ValueError, TypeError):
            return f"Error: delay_seconds must be an integer, got {delay_seconds!r}."
        if delay <= 0:
            return "Error: delay_seconds must be greater than 0."
        execute_at = now_utc + timedelta(seconds=delay)
    elif execute_at_utc:
        try:
            execute_at = datetime.fromisoformat(execute_at_utc)
        except ValueError:
            return (
                f"Error: invalid execute_at_utc format '{execute_at_utc}'. "
                "Use YYYY-MM-DDTHH:MM:SS in UTC. "
                "Remember: IST is UTC+5:30, so subtract 5h30m from the IST time."
            )
    else:
        return "Error: provide either delay_seconds (for relative times) or execute_at_utc (for absolute times)."

    if execute_at <= now_utc:
        return (
            f"Error: scheduled time ({execute_at.isoformat()}) is in the past. "
            "Check timezone. If you specified IST, subtract 5h30m to get UTC."
        )

    # For relative reminder schedules, auto-fill missing set_alarm time fields.
    if tool_name == "set_alarm":
        if tool_args.get("hour") is None or tool_args.get("minute") is None:
            ist_dt = execute_at + IST_OFFSET
            tool_args["hour"] = ist_dt.hour
            tool_args["minute"] = ist_dt.minute
        if not tool_args.get("label"):
            tool_args["label"] = description or "Reminder"

    validation_error = _validate_scheduled_tool(tool_name, tool_args, description)
    if validation_error:
        return validation_error

    task_id = add_task(
        session_id=session_id,
        user_id=user_id,
        tool_name=tool_name,
        tool_args=tool_args,
        execute_at=execute_at,
        description=description,
        google_token=google_token,
    )

    delta = execute_at - now_utc
    total_s = int(delta.total_seconds())
    if total_s < 60:
        when = f"in {total_s}s"
    elif total_s < 3600:
        when = f"in {total_s // 60} min"
    else:
        h, m = total_s // 3600, (total_s % 3600) // 60
        when = f"in {h}h {m}min"

    return f"Task [{task_id}] scheduled: '{description}' - will run {when}."

async def _safe_execute(tool_name: str, tool_args: dict, google_token) -> str:
    """Wrap execute_tool with a structured error so the LLM gets clean feedback."""
    try:
        return await execute_tool(tool_name, tool_args, google_token)
    except Exception as e:
        return f"Tool '{tool_name}' encountered an error: {str(e)}"

