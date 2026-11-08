import warnings
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path

HERE = Path(__file__).parent
CREDENTIALS = HERE / "credentials.json"
TOKEN = HERE / "token.json"
# only reads the calendar, nothing is changed there
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


@dataclass
class WorkEvent:
    id: str
    title: str
    start: datetime
    end: datetime


def connect():
    # Google's libraries warn on every run that Python 3.10 won't get their future updates; it still works
    warnings.filterwarnings("ignore", category=FutureWarning, module=r"google\.")
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        raise RuntimeError("Google Calendar support needs: pip install -r requirements.txt")
    if not CREDENTIALS.exists():
        raise RuntimeError(f"Missing {CREDENTIALS.name}, see 'Google Calendar setup' in the README")

    from google.auth.exceptions import RefreshError

    creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES) if TOKEN.exists() else None
    if creds and not creds.valid and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except RefreshError:
            # Google expires the sign-in about once a week while the app is in testing mode
            creds = None
    if not creds or not creds.valid:
        print("Signing in to Google, a browser window will open (or use the link below).")
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


def work_events(service, calendar_id, start, end):
    # timed events from start to end (both dates included), all-day ones aren't worked hours
    time_min = datetime.combine(start, time.min).astimezone().isoformat()
    time_max = datetime.combine(end + timedelta(days=1), time.min).astimezone().isoformat()
    events, page = [], None
    while True:
        result = service.events().list(
            calendarId=calendar_id, timeMin=time_min, timeMax=time_max,
            singleEvents=True, orderBy="startTime", pageToken=page,
        ).execute()
        for item in result.get("items", []):
            if "dateTime" not in item["start"] or item.get("status") == "cancelled":
                continue
            events.append(WorkEvent(
                id=item["id"],
                title=item.get("summary", "(no title)"),
                start=local(item["start"]["dateTime"]),
                end=local(item["end"]["dateTime"]),
            ))
        page = result.get("nextPageToken")
        if not page:
            return events


def local(timestamp):
    # "2026-10-29T08:00:00+01:00" -> naive local time
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone().replace(tzinfo=None)
