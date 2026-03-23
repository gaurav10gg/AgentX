# agent/toolRouter.py
import asyncio
import json
from typing import Dict, Any, Optional
from config.settings import settings

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "send_email",
            "description": "Send an email via Gmail",
            "parameters": {
                "type": "object",
                "properties": {
                    "to":      {"type": "string", "description": "Recipient email"},
                    "subject": {"type": "string", "description": "Email subject"},
                    "body":    {"type": "string", "description": "Email body"},
                    "cc":      {"type": "string", "description": "CC email (optional)"},
                },
                "required": ["to", "subject", "body"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_emails",
            "description": "Read recent emails from Gmail",
            "parameters": {
                "type": "object",
                "properties": {
                    "query":       {"type": "string",  "description": "Search query e.g. 'from:professor'"},
                    "max_results": {"type": "integer", "description": "Max emails to return (default 5)"},
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_alarm",
            "description": "Set an alarm on the user's Android phone",
            "parameters": {
                "type": "object",
                "properties": {
                    "hour":   {"type": "integer", "description": "Hour in 24h format (0-23)"},
                    "minute": {"type": "integer", "description": "Minute (0-59)"},
                    "label":  {"type": "string",  "description": "Alarm label (optional)"},
                    "days":   {"type": "array", "items": {"type": "string"},
                               "description": "Repeat days e.g. ['monday', 'friday']"},
                },
                "required": ["hour", "minute"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_event",
            "description": "Create a Google Calendar event",
            "parameters": {
                "type": "object",
                "properties": {
                    "title":            {"type": "string"},
                    "date":             {"type": "string", "description": "YYYY-MM-DD"},
                    "time":             {"type": "string", "description": "HH:MM (24h)"},
                    "duration_minutes": {"type": "integer"},
                    "description":      {"type": "string"},
                },
                "required": ["title", "date", "time"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_contact",
            "description": "Look up a contact's email or phone from Google Contacts",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Contact name to search for"},
                },
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for current information",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_events",
            "description": "Get upcoming Google Calendar events",
            "parameters": {
                "type": "object",
                "properties": {
                    "days_ahead": {"type": "integer", "description": "How many days ahead (default 7)"},
                },
                "required": []
            }
        }
    },
]

async def execute_tool(tool_name: str, tool_args: Dict, google_token: Optional[str] = None) -> str:
    try:
        return await asyncio.wait_for(
            _run_tool(tool_name, tool_args, google_token),
            timeout=settings.tool_timeout_seconds
        )
    except asyncio.TimeoutError:
        return f"Error: '{tool_name}' timed out after {settings.tool_timeout_seconds}s"
    except Exception as e:
        return f"Error running '{tool_name}': {str(e)}"

async def _run_tool(tool_name: str, args: Dict, google_token: Optional[str]) -> str:
    if tool_name == "send_email":
        from tools.gmail import send_email
        return await send_email(google_token, args["to"], args["subject"], args["body"], args.get("cc"))

    elif tool_name == "read_emails":
        from tools.gmail import read_emails
        return await read_emails(google_token, args.get("query", ""), args.get("max_results", 5))

    elif tool_name == "set_alarm":
        from tools.alarm import set_alarm
        return await set_alarm(args["hour"], args["minute"], args.get("label", "PhoneAgent"), args.get("days", []))

    elif tool_name == "create_event":
        from tools.calendar import create_event
        return await create_event(google_token, args["title"], args["date"], args["time"],
                                  args.get("duration_minutes", 60), args.get("description", ""))

    elif tool_name == "lookup_contact":
        from tools.contacts import lookup_contact
        return await lookup_contact(google_token, args["name"])

    elif tool_name == "web_search":
        from tools.search import web_search
        return await web_search(args["query"])

    elif tool_name == "get_events":
        from tools.calendar import get_events
        return await get_events(google_token, args.get("days_ahead", 7))

    else:
        return f"Unknown tool: {tool_name}"