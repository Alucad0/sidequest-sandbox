import argparse
import json
import math
import re
import sys
from dataclasses import dataclass
from decimal import Decimal
from datetime import date, datetime, timedelta
from pathlib import Path

import gcal
from medvind import BROWSERS, Medvind, MedvindError

HERE = Path(__file__).parent
SETTINGS = HERE / "settings.json"  # placement, time type, task and account to report on
REPORTED = HERE / "reported.json"  # calendar events already reported, so they're never reported twice
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
# KTH's schablonfaktor, preparation included: övningar count double, labs and the rest 1.8
FACTORS = {"övning": "2", "other": "1.8"}


def from_schedule_finder(title):
    # titles the schedule finder makes, like "DD1310-Övning"; "? DD1310-Övning" (not confirmed) and meetings don't match
    return re.match(r"[A-Z]{2}\d{4}[A-Z]?-\S", title) is not None


def factor_for(event, factors):
    _, _, activity = event.title.partition("-")
    return factors["övning"] if activity.strip().lower().startswith("övning") else factors["other"]


def worked_minutes(event):
    # sessions start a quarter past (10-12 is 1 h 45 min), except at 8:00 (8-10 is 2 h)
    worked = int((event.end - event.start).total_seconds()) // 60
    if (event.start.hour, event.start.minute) != (8, 0):
        worked -= 15
    return max(worked, 0)


def paid_minutes(event, factor):
    # worked time times the factor, always rounded UP to whole quarters: 8-10 lab -> 2 h * 1.8 = 3.6 h -> 3 h 45 min
    return math.ceil(worked_minutes(event) * Decimal(factor) / 15) * 15


def hours(minutes):
    # 195 -> "3.25h", 120 -> "2h"
    return f"{Decimal(minutes) / 60:f}".rstrip("0").rstrip(".") + "h"


@dataclass
class Entry:
    event: gcal.WorkEvent
    start: datetime  # the reported time, which ends when the session ends
    end: datetime
    factor: str = "1"
    moved: bool = False  # moved later, the planned time was taken in Medvind
    status: str = ""  # empty = can be reported

    @property
    def day(self):
        return self.event.start.date()

    def comment(self):
        # "DD1310-Datorlaboration" for CMATD1, COPEN1 at 16:00-18:00 with Vahid Mosavat
        # -> "DD1310-labb, Vahid Mosavat, CMATD/COPEN, 16-18, 1.75h*1.8=3.15h up to 3.25h" (rounded up to a quarter)
        course, _, activity = self.event.title.partition("-")
        worked = worked_minutes(self.event)
        exact = Decimal(worked) * Decimal(self.factor)
        calculation = f"{hours(worked)}*{self.factor}={hours(exact)}"
        paid = paid_minutes(self.event, self.factor)
        if paid != exact:
            calculation += f" up to {hours(paid)}"
        parts = [f"{course.strip()}-{short(activity)}", teacher(self.event.description), classes(self.event.description),
                 f"{clock(self.event.start)}-{clock(self.event.end)}", calculation]
        # Medvind stores <, > and & escaped twice, so they're left out
        return re.sub(r"[<>&]", "", ", ".join(p for p in parts if p))

    def interval(self, settings):
        return {
            "dygn": "0",
            "start": str(minutes(self.start)),
            "slut": str(minutes(self.end)),
            "tidtyp": settings["time_type"],
            "uppgift": settings["task"],
            "avvkonto": settings["account"],
            "tidtyp_orsak": self.comment(),
        }


def short(activity):
    # TimeEdit's activity names, shortened the way they're written by hand
    activity = activity.strip().lower()
    if "laboration" in activity:
        return "labb"
    if activity.startswith("övning"):
        return "övn"
    return activity


def classes(description):
    # the schedule finder's programme line, "CMATD1, COPEN1" -> "CMATD/COPEN"
    for line in description.splitlines():
        codes = [c.strip() for c in line.split(",")]
        if codes and all(re.fullmatch(r"[A-Z]{4,6}\d?", c) for c in codes):
            return "/".join(dict.fromkeys(c.rstrip("0123456789") for c in codes))
    return ""


def teacher(description):
    # the schedule finder's "Teacher: Vahid Mosavat" line, the course coordinator in TimeEdit
    for line in description.splitlines():
        if line.startswith("Teacher:"):
            return line.removeprefix("Teacher:").strip()
    return ""


def clock(t):
    return f"{t.hour}" if t.minute == 0 else f"{t.hour}:{t.minute:02d}"


def clock_hm(minutes_after_midnight):
    return f"{minutes_after_midnight // 60:02}:{minutes_after_midnight % 60:02}"


def minutes(t):
    return t.hour * 60 + t.minute


def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def save_json(path, data):
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")


def reportable(plantext):
    # KTH has placements that say "RAPPORTERA EJ TID HÄR", time must never go there
    text = plantext.lower()
    return "rapportera ej" not in text and "rapportera inte" not in text


def setup(medvind):
    # pick the placement once, and copy time type, task and account from the last shift reported there by hand
    placements = {}
    for entry in medvind.load_day(date.today()):
        if reportable(entry.get("plantext", "")):
            placements[(entry["anstnr"], entry["planid"])] = entry["plantext"]
    if not placements:
        sys.exit("Found no Medvind placement to report on")
    choices = sorted(placements.items())
    print("\nWhich placement should hours be reported on?")
    for n, ((anstnr, _), text) in enumerate(choices, 1):
        print(f"  {n} {text}, Anstnr: {anstnr}")
    while True:
        answer = input("Placement: ").strip()
        if answer.isdigit() and 1 <= int(answer) <= len(choices):
            break
    (anstnr, planid), plantext = choices[int(answer) - 1]
    placement = {"anstnr": anstnr, "planid": planid, "plantext": plantext}

    for day in reversed(medvind.worked_days(placement, date.today() - timedelta(days=365), date.today())):
        for entry in medvind.load_day(date.fromisoformat(day)):
            if entry["anstnr"] == anstnr and entry["planid"] == planid and entry.get("intv"):
                last = entry["intv"][-1]
                settings = {
                    "placement": placement,
                    "time_type": last["tidtyp"], "time_type_text": last.get("tidtyp_text", ""),
                    "task": last.get("uppgift", ""), "task_text": last.get("uppgift_text", ""),
                    "account": last.get("avvkonto", ""),
                }
                save_json(SETTINGS, settings)
                print(f"Saved in {SETTINGS.name}: {settings['time_type_text']}, {settings['task_text']}, "
                      f"account {settings['account']} (copied from your shift on {day})")
                return settings
    sys.exit("Report one shift on that placement by hand first, so its time type and account can be copied")


def plan(events, factors):
    # each session is reported as its paid time ending when the session ends; check() moves it if that time is taken
    entries = []
    for event in sorted(events, key=lambda e: e.start):
        factor = factor_for(event, factors)
        entries.append(Entry(event, event.end - timedelta(minutes=paid_minutes(event, factor)), event.end, factor))
    return entries


def place(entry, busy):
    # the start (minutes after midnight) of the first free slot, from the planned one and later in whole quarters
    length = int((entry.end - entry.start).total_seconds()) // 60
    start = minutes(entry.end) - length
    while start + length <= 24 * 60:
        clash = [b for b in busy if b[0] < start + length and start < b[1]]
        if start >= 0 and not clash:
            return start
        later = max([start, 0] + [b[1] for b in clash])
        start = max(math.ceil(later / 15) * 15, start + 15)
    return None


def check(entries, medvind, settings, reported):
    # mark what can't or shouldn't be reported, move shifts off time that's already planned,
    # and keep each day's Medvind entry for saving
    placement = settings["placement"]
    loaded, own, taken = {}, {}, {}
    now = datetime.now()
    # shifts this program reported, so they aren't mistaken for ones reported by hand
    ours = {(r["date"], r["start"], r["end"]) for r in reported.values()}
    for entry in entries:
        if entry.event.id in reported:
            entry.status = "already reported"
            done = reported[entry.event.id]
            entry.start = datetime.fromisoformat(f"{done['date']}T{done['start']}")
            entry.end = datetime.fromisoformat(f"{done['date']}T{done['end']}")
        elif entry.event.end > now:
            entry.status = "not worked yet"
        if entry.status:
            continue
        if entry.day not in loaded:
            loaded[entry.day] = medvind.load_day(entry.day)
            own[entry.day] = next((e for e in loaded[entry.day]
                                   if e["anstnr"] == placement["anstnr"] and e["planid"] == placement["planid"]), None)
            # every placement's shifts count as busy, like the daily planning on another placement
            taken[entry.day] = [(int(i["start"]), int(i["slut"])) for e in loaded[entry.day] for i in e.get("intv", [])]
        day = own[entry.day]
        session = (minutes(entry.event.start), minutes(entry.event.end))
        if day is None:
            entry.status = "placement not open that day"
        elif day.get("readonly") == "1":
            entry.status = day.get("readonly_reason") or "locked"
        elif any(int(i["start"]) < session[1] and session[0] < int(i["slut"])
                 and (entry.day.isoformat(), clock_hm(int(i["start"])), clock_hm(int(i["slut"]))) not in ours
                 for i in day.get("intv", [])):
            # a shift on your placement during the session itself, most likely reported by hand
            entry.status = "already in Medvind"
        else:
            start = place(entry, taken[entry.day])
            if start is None:
                entry.status = "no free time that day"
                continue
            length = entry.end - entry.start
            moved = datetime.combine(entry.day, datetime.min.time()) + timedelta(minutes=start)
            entry.moved = moved != entry.start
            entry.start, entry.end = moved, moved + length
            taken[entry.day].append((start, start + int(length.total_seconds()) // 60))
    return own


def show(entries):
    numbered = []
    for entry in entries:
        if entry.status:
            mark = "✓" if entry.status == "already reported" else "✗"
        else:
            numbered.append(entry)
            mark = str(len(numbered))
        e = entry.event
        length = (entry.end - entry.start).total_seconds() / 3600
        moved = " (moved, time taken)" if entry.moved and not entry.status else ""
        print(f"  {mark:>2} {DAYS[e.start.weekday()]} {e.start:%d %b}  {e.start:%H:%M}-{e.end:%H:%M}  {e.title:<18}"
              f" -> {entry.start:%H:%M}-{entry.end:%H:%M} {length:4.2f} h  {entry.status or entry.comment()}{moved}")
    return numbered


def parse_selection(text, count):
    # "1 3 5-8" or "all" -> [0, 2, 4, 5, 6, 7]
    if text.strip().lower() == "all":
        return list(range(count))
    chosen = set()
    for part in text.replace(",", " ").split():
        first, _, last = part.partition("-")
        if not first.isdigit() or (last and not last.isdigit()):
            raise ValueError(f"'{part}' isn't a number from the list")
        for n in range(int(first), int(last or first) + 1):
            if not 1 <= n <= count:
                raise ValueError(f"There is no {n} in the list")
            chosen.add(n - 1)
    return sorted(chosen)


def pick(entries):
    while True:
        answer = input("\nWhich do you want to report in Medvind? (e.g. 1 3 5-8, all, Enter for none): ")
        try:
            return [entries[i] for i in parse_selection(answer, len(entries))]
        except ValueError as error:
            print(error)


def report(chosen, days, medvind, settings, reported):
    done = 0
    for day in sorted({e.day for e in chosen}):
        new = [e for e in chosen if e.day == day]
        entry = dict(days[day])
        # the day is saved as a whole, so the shifts already on it are sent again unchanged
        entry["intv"] = list(entry.get("intv", [])) + [e.interval(settings) for e in new]
        try:
            medvind.save_day(entry, day)
        except MedvindError as error:
            print(f"  {day}: not saved, Medvind said: {error}")
            continue
        # read the day back to be sure the shifts are really there
        saved = next((e for e in medvind.load_day(day)
                      if e["anstnr"] == entry["anstnr"] and e["planid"] == entry["planid"]), {})
        there = {(int(i["start"]), int(i["slut"])): i.get("tidtyp_orsak", "") for i in saved.get("intv", [])}
        for e in new:
            key = (minutes(e.start), minutes(e.end))
            if key in there:
                if there[key].strip() != e.comment():
                    print(f"  {day} {e.event.title}: Medvind changed the comment to {there[key]!r}")
                reported[e.event.id] = {"date": day.isoformat(), "start": f"{e.start:%H:%M}", "end": f"{e.end:%H:%M}",
                                        "title": e.event.title, "anstnr": entry["anstnr"]}
                done += 1
            else:
                print(f"  {day} {e.event.title}: saved, but it isn't in Medvind when reading the day back")
        save_json(REPORTED, reported)
    print(f"Reported {done} of {len(chosen)} in Medvind, they still need your manager's approval")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    today = date.today()
    first_of_last_month = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
    parser = argparse.ArgumentParser(description="Report the events in your WORK calendar as worked hours in Medvind.")
    parser.add_argument("--from", dest="start", type=date.fromisoformat, default=first_of_last_month,
                        help="YYYY-MM-DD, default the first day of last month")
    parser.add_argument("--to", dest="end", type=date.fromisoformat, default=today, help="YYYY-MM-DD, default today")
    parser.add_argument("--factor", default=FACTORS["other"], help=f"schablonfaktor for labs and the rest (default {FACTORS['other']})")
    parser.add_argument("--factor-ovning", default=FACTORS["övning"], help=f"schablonfaktor for övningar (default {FACTORS['övning']})")
    parser.add_argument("--calendar", default="WORK", help="Google Calendar to read (default WORK)")
    parser.add_argument("--browser", default="auto", choices=BROWSERS,
                        help="browser to log in with (default auto: Chrome, else Edge, else Playwright's Chromium)")
    parser.add_argument("--setup", action="store_true", help="pick the Medvind placement again")
    parser.add_argument("--dry-run", action="store_true", help="show what would be reported without reporting it")
    args = parser.parse_args()
    if args.end < args.start:
        parser.error("--to is before --from")

    print(f"Reading {args.calendar}, {args.start} to {args.end}")
    try:
        service = gcal.connect()
        events = gcal.work_events(service, gcal.find_calendar(service, args.calendar), args.start, args.end)
    except (LookupError, RuntimeError) as error:
        sys.exit(str(error))
    others = sum(not from_schedule_finder(e.title) for e in events)
    events = [e for e in events if from_schedule_finder(e.title)]
    if others:
        print(f"  {others} events left out (not from the schedule finder, or marked with ?)")
    if not events:
        print("No sessions, nothing to report")
        return
    factors = {"övning": args.factor_ovning, "other": args.factor}
    entries = plan(events, factors)

    print("Opening Medvind")
    try:
        medvind = Medvind(args.browser)
    except (MedvindError, RuntimeError) as error:
        sys.exit(f"Medvind: {error}")
    try:
        medvind.open()
        settings = None if args.setup else load_json(SETTINGS) or None
        settings = settings or setup(medvind)
        if not reportable(settings["placement"]["plantext"]):
            sys.exit(f"{settings['placement']['plantext']} must not be reported on, run with --setup")
        reported = load_json(REPORTED)
        days = check(entries, medvind, settings, reported)

        print(f"\n{settings['placement']['plantext']}, Anstnr: {settings['placement']['anstnr']}"
              f"  ({settings.get('time_type_text', '')}, account {settings['account']}, factor {args.factor}, övning {args.factor_ovning})")
        numbered = show(entries)
        if not numbered:
            print("\nNothing new to report")
            return
        if args.dry_run:
            print(f"\nDry run, {len(numbered)} could be reported")
            return
        chosen = pick(numbered)
        if not chosen:
            return
        # plan again with only the picked events, so one left out doesn't push the others later
        chosen = plan([e.event for e in chosen], factors)
        days.update(check(chosen, medvind, settings, reported))
        if any(e.status for e in chosen):
            print("\nSome can't be reported after all:")
            show([e for e in chosen if e.status])
        chosen = [e for e in chosen if not e.status]
        if chosen:
            print("\nReporting:")
            show(chosen)
            report(chosen, days, medvind, settings, reported)
    except MedvindError as error:
        sys.exit(f"Medvind: {error}")
    finally:
        medvind.close()


if __name__ == "__main__":
    main()
