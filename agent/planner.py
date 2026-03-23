# agent/planner.py
from typing import List
from providers.base import BaseLLMProvider

PLANNER_PROMPT = """You are a task planner for a personal AI agent that controls a phone.

Break the user's request into a numbered list of concrete steps.
Each step = ONE tool call or ONE reasoning step.

Available tools:
send_email, read_emails, search_emails, set_alarm, cancel_alarm,
create_event, get_events, check_free_time, lookup_contact,
web_search, set_reminder

Rules:
- Max 5 steps. If it's a 1-step task, return 1 step.
- Return ONLY the numbered list. No explanations.

Example:
User: "Email my professor about leave for 4 days starting Monday"
1. lookup_contact("professor") to get email address
2. check_free_time("Monday to Thursday") to confirm dates
3. send_email(to=professor_email, subject="Leave Application", body=formal_email)
"""

async def plan_task(user_message: str, llm: BaseLLMProvider) -> List[str]:
    response = await llm.chat(
        messages=[{"role": "user", "content": user_message}],
        system_prompt=PLANNER_PROMPT,
        temperature=0.1,
    )
    steps = []
    for line in response.strip().split("\n"):
        line = line.strip()
        if line and (line[0].isdigit() or line.startswith("-")):
            clean = line.lstrip("0123456789.-) ").strip()
            if clean:
                steps.append(clean)
    return steps if steps else [user_message]