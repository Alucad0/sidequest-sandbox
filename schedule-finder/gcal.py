from datetime import datetime, time, timedelta
from pathlib import Path

HERE = Path(__file__).parent
CREDENTIALS = HERE / "credentials.json"
TOKEN = HERE / "token.json"
SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",  # to find the calendar by name
    "https://www.googleapis.com/auth/calendar.events",  # to add events
]
TIMEZONE = "Europe/Stockholm"


def connect():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        raise RuntimeError("Google Calendar support needs: pip install -r requirements.txt")
    if not CREDENTIALS.exists():
        raise RuntimeError(f"Missing {CREDENTIALS.name}, see 'Google Calendar setup' in the README")

    creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES) if TOKEN.exists() else None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # opens the browser once to sign in, after that the saved token is reused
            creds = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS), SCOPES).run_local_server(port=0)
        TOKEN.write_text(creds.to_json())
    return build("calendar", "v3", credentials=creds)


def find_calendar(service, name):
    page = None
    while True:
        result = service.calendarList().list(pageToken=page).execute()
        for calendar in result["items"]:
            if calendar.get("summaryOverride", calendar["summary"]).lower() == name.lower():
                return calendar["id"]
        page = result.get("nextPageToken")
        if not page:
            raise LookupError(f"No calendar called {name} in your Google Calendar")


def busy_events(service, calendar_id, name, start, end):
    # everything already in the calendar between two dates, as TimeEdit-style events
    from timeedit import Event

    time_min = datetime.combine(start, time.min).astimezone().isoformat()
    time_max = datetime.combine(end + timedelta(days=1), time.min).astimezone().isoformat()
    events, page = [], None
    while True:
        result = service.events().list(
            calendarId=calendar_id, timeMin=time_min, timeMax=time_max,
            singleEvents=True, orderBy="startTime", pageToken=page,
        ).execute()
        for item in result.get("items", []):
            # all-day events (holidays, reminders) don't block a time slot
            if "dateTime" not in item["start"]:
                continue
            events.append(Event(
                # sessions added by this program keep their TimeEdit id, so they can be recognised
                id=item["id"].removeprefix("timeedit"),
                start=local(item["start"]["dateTime"]),
                end=local(item["end"]["dateTime"]),
                activity=item.get("summary", "(no title)"),
                groups="", programs="", offering="", teacher="", info="",
                room=item.get("location", ""),
                course=f"{name}:",
            ))
        page = result.get("nextPageToken")
        if not page:
            return events


def local(timestamp):
    # "2026-10-29T08:00:00+01:00" -> naive local time, like TimeEdit's
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone().replace(tzinfo=None)


def event_body(event):
    details = [event.group(), event.programs, event.offering, event.teacher and f"Teacher: {event.teacher}", event.info]
    return {
        # a fixed id per TimeEdit booking means adding the same session twice can't make a duplicate
        "id": f"timeedit{event.id}",
        "summary": f"{event.course}-{event.activity}",
        "location": event.room,
        "description": "\n".join(d for d in details if d),
        "start": {"dateTime": event.start.isoformat(), "timeZone": TIMEZONE},
        "end": {"dateTime": event.end.isoformat(), "timeZone": TIMEZONE},
    }


def add_events(service, calendar_id, events):
    from googleapiclient.errors import HttpError

    added = updated = 0
    for event in events:
        body = event_body(event)
        try:
            service.events().insert(calendarId=calendar_id, body=body).execute()
            added += 1
        except HttpError as error:
            if error.resp.status != 409:
                raise
            # already added once (Google also keeps deleted events), so bring that one up to date instead
            body["status"] = "confirmed"
            service.events().update(calendarId=calendar_id, eventId=body["id"], body=body).execute()
            updated += 1
    return added, updated
