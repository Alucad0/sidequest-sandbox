import argparse
import re
import shlex
import sys
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta
from urllib.error import URLError

import gcal
from timeedit import course_events, find_course, link_events

TEACHING_ACTIVITIES = ["Laboration", "Datorlaboration", "Övning"]
# re-exams and completions aren't something you attend just for taking the course
SKIP_WHEN_TAKING = {"Omtenta", "Omexamination", "FX-komplettering"}


@dataclass
class Restriction:
    filters: list
    activities: list

    def describe(self):
        text = "+".join(self.filters).upper()
        if self.activities:
            text += "@" + "/".join(self.activities)
        return text


def end_of_term(today):
    # autumn term ends mid-January, spring term mid-June
    if today < date(today.year, 1, 20):
        return date(today.year, 1, 20)
    if today < date(today.year, 6, 15):
        return date(today.year, 6, 15)
    return date(today.year + 1, 1, 20)


def plain(text):
    # "Övning" -> "ovning", so "ovning" and "övning" both work
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def parse_course(spec):
    # "DD1310:TINTE,grupp C@datorlab/övning" -> ("DD1310", Restriction(["tinte", "grupp c"], ["datorlab", "övning"]))
    # "+" works like "," between filters
    spec, _, activities = spec.partition("@")
    code, _, filters = spec.partition(":")
    return code.strip().upper(), Restriction(
        filters=[f.strip().lower() for f in re.split(r"[,+]", filters) if f.strip()],
        activities=[a.strip().lower() for a in re.split(r"[/,]", activities) if a.strip()],
    )


def group_specs(specs):
    # the same course given twice means either restriction: DD1310:COPEN+CMATD DD1310:TINTE
    courses = {}
    for spec in specs:
        code, restriction = parse_course(spec)
        courses.setdefault(code, []).append(restriction)
    return courses


def in_group(groups, mine):
    # is group "c" part of "DD1310 grupp A-D"? whole-class events (no "grupp") count for everyone
    groups = groups.lower()
    if "grupp" not in groups:
        return True
    for first, last in re.findall(r"grupp(?:er)?\s+(\w+)(?:\s*-\s*(\w+))?", groups):
        if mine == first or (last and len(mine) == len(first) == len(last) and first <= mine <= last):
            return True
    return False


def matches(event, filters):
    text = f"{event.groups} {event.programs} {event.offering} {event.info}".lower()
    for f in filters:
        if f.startswith("grupp "):
            if not in_group(event.groups, f.removeprefix("grupp ").strip()):
                return False
        elif f not in text:
            return False
    return True


def activity_matches(activity, wanted):
    # "datorlab" matches "Datorlaboration"; no list means every activity
    return wanted is None or any(plain(activity).startswith(plain(w)) for w in wanted)


def load_course(code, restrictions, start, end, default_activities=None, ask=False):
    object_id, name = find_course(code)
    all_events = course_events(object_id, code, start, end)
    if ask:
        # every class can have its own activities, so ask for each one; an @ typed at the prompt is the default
        for r in restrictions:
            r.activities = ask_activities(code, r, [e for e in all_events if matches(e, r.filters)], r.activities or default_activities)
    events = [
        e for e in all_events
        if any(matches(e, r.filters) and activity_matches(e.activity, r.activities or default_activities) for r in restrictions)
    ]
    described = " or ".join(r.describe() for r in restrictions if r.filters or r.activities)
    return name + (f" [{described}]" if described else ""), events


def ask_activities(code, restriction, events, default):
    # lists the activity types this class actually has, e.g. "1 Datorlaboration (12)"
    counts = {}
    for e in events:
        if e.activity:
            counts[e.activity] = counts.get(e.activity, 0) + 1
    if not counts:
        return restriction.activities
    names = sorted(counts)
    title = code + (":" + "+".join(restriction.filters).upper() if restriction.filters else "")
    print(f"\nActivities in {title}:")
    for i, name in enumerate(names, 1):
        print(f"  {i:>2} {name} ({counts[name]})")
    while True:
        answer = input(f"Which do you teach? (e.g. 1 3, all, Enter for {'/'.join(default)}): ")
        if not answer.strip():
            return restriction.activities
        try:
            return [names[i] for i in parse_selection(answer, len(names))]
        except ValueError as error:
            print(error)


def overlaps(a, b, buffer=timedelta(0)):
    return a.start < b.end + buffer and b.start < a.end + buffer


def report(name, sessions, busy, booked, buffer, free_only, numbered):
    # booked maps a TimeEdit id to its calendar entry
    # a session already in the calendar shouldn't clash with its own calendar entry
    clashes = {s.id: [b for b in busy if b.id != s.id and overlaps(s, b, buffer)] for s in sessions}
    # booked only counts when the calendar entry is still at TimeEdit's time; a moved one is listed so it can be fixed
    in_place = {s.id for s in sessions if s.id in booked and (booked[s.id].start, booked[s.id].end) == (s.start, s.end)}
    free = [s for s in sessions if not clashes[s.id] and s.id not in in_place]
    print(f"\n{name}")
    print(f"{len(sessions)} sessions, {len(free)} fit your schedule")

    week = None
    for s in sessions:
        if free_only and (clashes[s.id] or s.id in in_place):
            continue
        if s.start.isocalendar()[1] != week:
            week = s.start.isocalendar()[1]
            print(f"\n  Week {week}")
        entry = booked.get(s.id)
        if s.id in in_place:
            mark = "  ★"
        elif clashes[s.id]:
            mark = "  ✗"
        else:
            # free sessions get a number so they can be picked for the calendar
            numbered.append(s)
            mark = f"{len(numbered):>3}"
        who = s.group() + (f" ({s.programs})" if s.programs else "")
        line = f"  {mark} {s.start:%a %d %b %H:%M}-{s.end:%H:%M}  {s.activity:<15} {who}"
        if s.id in in_place:
            line += "   already booked" + (" (maybe)" if is_maybe(entry.activity) else "")
        elif clashes[s.id]:
            line += "   clashes with " + "; ".join(f"{b.label()} {b.start:%H:%M}" for b in clashes[s.id][:2])
        if entry and s.id not in in_place:
            line += f"   {'but ' if clashes[s.id] else ''}in {entry.course.rstrip(':')} at {entry.start:%a %d %b %H:%M}-{entry.end:%H:%M}"
            if not clashes[s.id]:
                line += ", pick it to move it to this time"
        print(line)


def is_maybe(title):
    # "? DD1310-Övning" isn't confirmed yet
    return title.lstrip().startswith("?")


def parse_selection(text, count, allow_maybe=False):
    # "1 3 5-8" or "all" -> [0, 2, 4, 5, 6, 7]
    return sorted(parse_picks(text, count, allow_maybe))


def parse_picks(text, count, allow_maybe=True):
    # "1 ?3 5-6" -> {0: False, 2: True, 4: False, 5: False}, where True means maybe ("?" in front)
    chosen = {}
    for part in text.replace(",", " ").split():
        maybe = part.startswith("?")
        if maybe:
            if not allow_maybe:
                raise ValueError(f"'{part}' isn't a number from the list")
            part = part[1:]
        if part.lower() == "all":
            chosen.update({i: maybe for i in range(count)})
            continue
        first, _, last = part.partition("-")
        if not first.isdigit() or (last and not last.isdigit()):
            raise ValueError(f"'{part}' isn't a number from the list")
        for n in range(int(first), int(last or first) + 1):
            if not 1 <= n <= count:
                raise ValueError(f"There is no {n} in the list")
            chosen[n - 1] = maybe
    return chosen


def pick(name, sessions):
    # returns the picked sessions and the ids of the ones marked as maybe
    while True:
        answer = input(f"\nWhich sessions do you want in {name}? (e.g. 1 3 5-8, ?4 for maybe, all, Enter for none): ")
        try:
            picks = parse_picks(answer, len(sessions))
        except ValueError as error:
            print(error)
            continue
        chosen = sorted(picks)
        # two picked sessions at the same time would be a double booking too
        overlapping = [(a + 1, b + 1) for i, a in enumerate(chosen) for b in chosen[i + 1:] if overlaps(sessions[a], sessions[b])]
        if overlapping:
            print("These overlap each other: " + ", ".join(f"{a} and {b}" for a, b in overlapping))
            continue
        return [sessions[i] for i in chosen], {sessions[i].id for i in chosen if picks[i]}


def ask_list(prompt):
    # shlex keeps quoted filters like "grupp C" together
    return shlex.split(input(prompt))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Find labs and övningar to teach that don't clash with the courses you take.")
    parser.add_argument("--taking", nargs="*", default=[], metavar="CODE[:FILTER]",
                        help="courses you take, e.g. SF1625:CITEH2 to only count events for your programme or group")
    parser.add_argument("--link", nargs="*", default=[], metavar="URL",
                        help="your own TimeEdit schedule link (.ics or .html), counted as busy")
    parser.add_argument("--teaching", nargs="*", default=[], metavar="CODE[:FILTER][@ACTIVITIES]",
                        help="courses you teach, e.g. DD1310:TINTE@datorlab/övning")
    parser.add_argument("--activities", nargs="*", default=TEACHING_ACTIVITIES,
                        help=f"activity types to look for when a course has no @ (default: {' '.join(TEACHING_ACTIVITIES)})")
    parser.add_argument("--from", dest="start", type=date.fromisoformat, default=date.today(), help="YYYY-MM-DD, default today")
    parser.add_argument("--to", dest="end", type=date.fromisoformat, help="YYYY-MM-DD, default end of term")
    parser.add_argument("--buffer", type=int, default=0, help="minutes needed between sessions, e.g. to change campus")
    parser.add_argument("--free-only", action="store_true", help="hide the sessions that clash or are already booked")
    parser.add_argument("--calendar", default="WORK", help="Google Calendar to check and add sessions to (default WORK)")
    parser.add_argument("--no-calendar", action="store_true", help="don't use Google Calendar, only list the sessions")
    parser.add_argument("--dry-run", action="store_true", help="read the calendar but show what would be added instead of adding it")
    args = parser.parse_args()

    interactive = not (args.taking or args.link or args.teaching)
    if interactive:
        print("Courses you take, separated by spaces. Add your programme and group to only count your own events,")
        print('e.g. SF1672:CTFYS1,"grupp C" (use quotes when there is a space).')
        args.taking = ask_list("Taking: ")
        args.link = ask_list("Your TimeEdit schedule link, if you have one (Enter to skip): ")
        print("Courses you teach. Add the class after :, and repeat the course for each class, e.g. DD1310:COPEN+CMATD DD1310:TINTE")
        args.teaching = ask_list("Teaching: ")
    if not args.teaching:
        parser.error("give at least one course with --teaching")
    end = args.end or end_of_term(args.start)
    buffer = timedelta(minutes=args.buffer)
    print(f"Checking {args.start} to {end}")

    service = calendar_id = None
    busy, booked = [], {}
    if not args.no_calendar:
        try:
            service = gcal.connect()
            calendar_id = gcal.find_calendar(service, args.calendar)
            work = gcal.busy_events(service, calendar_id, args.calendar, args.start, end)
            print(f"  calendar {args.calendar}: {len(work)} events")
            busy += work
            booked = {e.id: e for e in work}
        except (LookupError, RuntimeError) as error:
            if not args.dry_run:
                sys.exit(f"{error}\n(use --no-calendar or --dry-run to run without Google Calendar)")
            print(f"  calendar {args.calendar}: not checked, {error}")
            service = None

    try:
        for code, restrictions in group_specs(args.taking).items():
            name, events = load_course(code, restrictions, args.start, end)
            events = [e for e in events if e.activity and e.activity not in SKIP_WHEN_TAKING]
            print(f"  taking   {name}: {len(events)} events")
            busy += events
        for url in args.link:
            events = [e for e in link_events(url, args.start, end) if e.activity not in SKIP_WHEN_TAKING]
            print(f"  schedule link: {len(events)} events")
            busy += events

        free = []
        for code, restrictions in group_specs(args.teaching).items():
            # when run without arguments, ask which activities to teach for each class
            name, sessions = load_course(code, restrictions, args.start, end, args.activities, ask=interactive)
            report(name, sessions, busy, booked, buffer, args.free_only, free)
    except (LookupError, ValueError) as error:
        sys.exit(str(error))
    except URLError as error:
        sys.exit(f"Couldn't reach TimeEdit ({error.reason})")

    if not free or args.no_calendar:
        return
    chosen, maybe = pick(args.calendar, free)
    if not chosen:
        return
    if args.dry_run or not service:
        print(f"\nDry run, these would be added to {args.calendar}:")
        for s in chosen:
            body = gcal.event_body(s, s.id in maybe)
            print(f"  {s.start:%a %d %b %H:%M}-{s.end:%H:%M}  {body['summary']}  @ {body['location']}")
        return
    added, updated = gcal.add_events(service, calendar_id, chosen, maybe)
    print(f"Added {added} sessions to {args.calendar}" + (f", updated {updated} that were already there" if updated else ""))


if __name__ == "__main__":
    main()
