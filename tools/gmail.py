# tools/gmail.py
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

def _get_service(token: dict):
    creds = Credentials(
        token=token["access_token"],
        refresh_token=token.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=token.get("client_id"),
        client_secret=token.get("client_secret"),
    )
    return build("gmail", "v1", credentials=creds)

async def send_email(
    token: dict,
    to: str,
    subject: str,
    body: str,
    cc: Optional[str] = None
) -> str:
    try:
        service = _get_service(token)
        msg = MIMEMultipart()
        msg["to"] = to
        msg["subject"] = subject
        if cc:
            msg["cc"] = cc
        msg.attach(MIMEText(body, "plain"))
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        return f"Email sent to {to} with subject '{subject}'"
    except Exception as e:
        return f"Failed to send email: {str(e)}"

async def read_emails(
    token: dict,
    query: str = "",
    max_results: int = 5
) -> str:
    try:
        service = _get_service(token)
        results = service.users().messages().list(
            userId="me", q=query or "in:inbox", maxResults=max_results
        ).execute()

        messages = results.get("messages", [])
        if not messages:
            return "No emails found."

        email_list = []
        for msg in messages:
            full = service.users().messages().get(
                userId="me", id=msg["id"], format="metadata",
                metadataHeaders=["From", "Subject", "Date"]
            ).execute()
            headers = {h["name"]: h["value"] for h in full["payload"]["headers"]}
            snippet = full.get("snippet", "")[:100]
            email_list.append(
                f"From: {headers.get('From', '?')}\n"
                f"Subject: {headers.get('Subject', 'No Subject')}\n"
                f"Date: {headers.get('Date', '')}\n"
                f"Preview: {snippet}..."
            )
        return "\n\n---\n\n".join(email_list)
    except Exception as e:
        return f"Failed to read emails: {str(e)}"

async def search_emails(token: dict, query: str) -> str:
    return await read_emails(token=token, query=query, max_results=10)