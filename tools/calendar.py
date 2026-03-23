# tools/calendar.py
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from datetime import datetime, timedelta
from typing import Optional

def _get_service(token: dict):
    creds = Credentials(
        token=token["access_token"],
        refresh_token=token.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=token.get("client_id"),
        client_secret=token.get("client_secret"),
    )
    return build("calendar", "v3", credentials=creds)

async def create_event(
    token: dict,
    title: str,
    date: str,
    time: str,
    duration_minutes: int = 60,
    description: str = ""
) -> str:
    try:
        service = _get_service(token)
        start_dt = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
        end_dt = start_dt + timedelta(minutes=duration_minutes)
        event = {
            "summary": title,
            "description": description,
            "start": {"dateTime": start_dt.isoformat(), "timeZone": "Asia/Kolkata"},
            "end":   {"dateTime": end_dt.isoformat(),   "timeZone": "Asia/Kolkata"},
        }
        created = service.events().insert(calendarId="primary", body=event).execute()
        return f"Event '{title}' created on {date} at {time} IST. Link: {created.get('htmlLink', '')}"
    except Exception as e:
        return f"Failed to create event: {str(e)}"

async def get_events(token: dict, days_ahead: int = 7) -> str:
    try:
        service = _get_service(token)
        now = datetime.utcnow().isoformat() + "Z"
        end = (datetime.utcnow() + timedelta(days=days_ahead)).isoformat() + "Z"
        results = service.events().list(
            calendarId="primary", timeMin=now, timeMax=end,
            maxResults=10, singleEvents=True, orderBy="startTime"
        ).execute()
        events = results.get("items", [])
        if not events:
            return f"No events in the next {days_ahead} days."
        return "\n".join([
            f"- {e['summary']} → {e['start'].get('dateTime', e['start'].get('date'))}"
            for e in events
        ])
    except Exception as e:
        return f"Failed to get events: {str(e)}"

async def check_free_time(token: dict, date: str) -> str:
    try:
        service = _get_service(token)
        dt = datetime.strptime(date, "%Y-%m-%d")
        start = dt.isoformat() + "Z"
        end = (dt + timedelta(days=1)).isoformat() + "Z"
        results = service.events().list(
            calendarId="primary", timeMin=start,
            timeMax=end, singleEvents=True
        ).execute()
        events = results.get("items", [])
        if not events:
            return f"{date} is completely free."
        busy = [f"{e['summary']} at {e['start'].get('dateTime', '')}" for e in events]
        return f"Busy on {date}: " + ", ".join(busy)
    except Exception as e:
        return f"Failed to check calendar: {str(e)}"