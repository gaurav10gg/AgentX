# tools/contacts.py
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
    return build("people", "v1", credentials=creds)

async def lookup_contact(token: dict, name: str) -> str:
    try:
        service = _get_service(token)
        results = service.people().searchContacts(
            query=name,
            readMask="names,emailAddresses,phoneNumbers"
        ).execute()
        contacts = results.get("results", [])
        if not contacts:
            return f"No contact found for '{name}'"
        person = contacts[0]["person"]
        names  = person.get("names", [])
        emails = person.get("emailAddresses", [])
        phones = person.get("phoneNumbers", [])
        display = names[0]["displayName"] if names else name
        email   = emails[0]["value"] if emails else "No email"
        phone   = phones[0]["value"] if phones else "No phone"
        return f"Contact: {display}\nEmail: {email}\nPhone: {phone}"
    except Exception as e:
        return f"Failed to lookup contact: {str(e)}"

async def list_contacts(token: dict) -> str:
    try:
        service = _get_service(token)
        results = service.people().connections().list(
            resourceName="people/me",
            pageSize=20,
            personFields="names,emailAddresses"
        ).execute()
        connections = results.get("connections", [])
        if not connections:
            return "No contacts found."
        output = []
        for p in connections:
            name  = p.get("names", [{}])[0].get("displayName", "Unknown")
            email = p.get("emailAddresses", [{}])[0].get("value", "No email")
            output.append(f"{name} — {email}")
        return "\n".join(output)
    except Exception as e:
        return f"Failed to list contacts: {str(e)}"