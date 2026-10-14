from __future__ import annotations

import html
import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta

BASE = "https://cloud.timeedit.net/kth/web/public01"
HEADERS = {"User-Agent": "schedule-finder (github.com/Alucad0/sidequest-sandbox)"}
COURSE_TYPE = 5


@dataclass(frozen=True)
class Event:
    id: str
    start: datetime
    end: datetime
    activity: str
    groups: str
    programs: str
    offering: str
    teacher: str
    room: str
    info: str
    course: str

    def group(self) -> str:
        # "DD1310 grupp H-N" -> "grupp H-N"
        return self.groups.removeprefix(self.course).strip()

    def label(self) -> str:
        return f"{self.course} {self.activity}" + (f" ({self.group()})" if self.group() else "")


def get(url: str) -> str:
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read().decode("utf-8")


def find_course(code: str) -> tuple[str, str]:
    # TimeEdit's object search, returns the object id and full name, e.g. ("381575.5", "DD1310, Programming Techniques")
    query = urllib.parse.urlencode({
        "max": 50, "fr": "t", "partajax": "t", "im": "f", "sid": 10, "l": "sv",
        "search_text": code, "objects": "", "types": COURSE_TYPE,
    })
    page = get(f"{BASE}/objects.html?{query}")
    matches = re.findall(r'data-id="([\d.]+)"[^>]*data-name="([^"]*)"', page)
    for object_id, name in matches:
        name = html.unescape(name)
        if name.split(",")[0].strip().upper() == code.upper():
            return object_id, name
    raise LookupError(f"No course called {code} on TimeEdit")


def month_chunks(start: date, end: date):
    # TimeEdit stops at 1000 bookings per request, so long ranges are fetched a month at a time
    while start <= end:
        stop = min(end, start + timedelta(days=30))
        yield start, stop
        start = stop + timedelta(days=1)


def course_events(object_id: str, course: str, start: date, end: date) -> list[Event]:
    events = {}
    for chunk_start, chunk_end in month_chunks(start, end):
        period = f"{chunk_start:%Y%m%d}.x,{chunk_end:%Y%m%d}.x"
        query = f"h=t&sid=3&p={period}&objects={object_id}&ox=0&types=0&fe=0"
        for event in parse(get(f"{BASE}/ri.json?{query}"), course):
            events[event.id] = event
    return sorted(events.values(), key=lambda e: e.start)


def link_events(url: str, start: date, end: date) -> list[Event]:
    # a personal TimeEdit link (the .ics you import into Google Calendar) also works as .json
    url = re.sub(r"\.(ics|html|csv)(\?|$)", r".json\2", url.strip())
    if not url.endswith(".json") and ".json?" not in url:
        raise ValueError("That doesn't look like a TimeEdit schedule link")
    events = parse(get(url), "")
    return [e for e in events if start <= e.start.date() <= end]


def parse(text: str, course: str) -> list[Event]:
    data = json.loads(text)
    if data["info"]["reservationcount"] > data["info"]["reservationlimit"]:
        print("Warning: TimeEdit cut the schedule short, try a shorter date range.")
    headers = [h.lower() for h in data["columnheaders"]]

    def column(row, *names):
        for name in names:
            for i, header in enumerate(headers):
                if header and name in header and i < len(row):
                    return row[i].strip()
        return ""

    events = []
    for r in data["reservations"]:
        row = r["columns"]
        offering = column(row, "tillfälle", "course event")
        events.append(Event(
            id=r["id"],
            start=datetime.fromisoformat(f"{r['startdate']}T{r['starttime']}"),
            end=datetime.fromisoformat(f"{r['enddate']}T{r['endtime']}"),
            activity=column(row, "aktivitet", "activity"),
            groups=column(row, "grupp", "group"),
            programs=column(row, "program"),
            offering=offering,
            # the teacher column has no header
            teacher=row[headers.index("")] if "" in headers and headers.index("") < len(row) else "",
            room=column(row, "lokal", "room", "location"),
            info=column(row, "info"),
            course=course or offering.split("-")[0].split(" ")[0],
        ))
    return events
