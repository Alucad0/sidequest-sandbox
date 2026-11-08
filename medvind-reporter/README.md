# Medvind reporter

Reports the sessions the [schedule finder](../schedule-finder/) put in your **WORK** Google Calendar as worked hours in Medvind, KTH's time reporting (KTH-HR → Egenrapportering → Min arbetstid).

Medvind has no API, so the script opens a browser window and you log in to KTH yourself. It never sees your password. It then makes the same calls Medvind's own page makes when you open and save a day.

## Usage

```bash
python medvind_reporter.py --from 2026-10-26 --to 2026-11-06
```

```output
Reading WORK, 2026-10-26 to 2026-11-06
  9 events left out (not from the schedule finder, or marked with ?)
Opening Medvind

Teoretisk datalogi Personal (JHT), Intermittent, Anstnr: 1234567:04  (Student(165), account JHT,110210,, 75 min prep)
   ✓ Wed 28 Oct  13:00-15:00  DD1310-Datorlaboration -> 11:45-15:00 3.25 h  already reported
   1 Wed 04 Nov  16:00-18:00  DD1310-Datorlaboration -> 14:45-18:00 3.25 h  DD1310, Datorlaboration kl 16-18
   2 Fri 06 Nov  13:00-14:00  DD1310-Övning      -> 11:45-14:00 2.25 h  DD1310, Övning kl 13-14

Which do you want to report in Medvind? (e.g. 1 3 5-8, all, Enter for none): all
```

Only events with a schedule finder title like `DD1310-Övning` are listed. Meetings and other events are left out, and so is a session marked as not confirmed with a `?` in front (`? DD1310-Övning`).

Each session is reported as:

- **Time:** labs and övningar get `--prep` minutes before them, other activities keep their own time. When picked shifts would overlap, the later one is moved later, keeping its length.
- **Comment:** e.g. `DD1310, Övning kl 13-15`, made from the title.
- **Time type, task and account:** copied from a shift you reported by hand (see Setup).

An event is never reported twice. Reported events are remembered in `reported.json`, and an event that overlaps time already in Medvind is skipped, for example one you reported by hand. So are sessions that haven't ended yet, and days in a locked (attested) period. After saving, each day is read back from Medvind to check the shifts are there.

## Options

| Option | |
|---|---|
| `--from`, `--to` | date range, `YYYY-MM-DD` (default the first day of last month to today) |
| `--prep MIN` | preparation minutes added before each lab or övning (default 75) |
| `--calendar NAME` | calendar to read instead of `WORK` |
| `--dry-run` | show what would be reported without reporting it |
| `--setup` | pick the Medvind placement again |
| `--browser` | `msedge` (default) or `chrome` |

## Setup

1. Install the packages:

   ```bash
   pip install -r requirements.txt
   ```

   Playwright drives your installed Edge (or Chrome with `--browser chrome`), so `playwright install` isn't needed.

2. Copy `credentials.json` from the [schedule finder](../schedule-finder/README.md#google-calendar-setup), or follow its Google Calendar setup. This program only reads the calendar.

3. Report one shift on your placement by hand in Medvind. On the first run you pick the placement, and its time type, task and account are copied from that shift into `settings.json`. Placements marked **RAPPORTERA EJ TID HÄR** are never offered or used.

Each run opens an Edge window where you log in to KTH yourself. The session is kept in `browser-profile/`, so a run soon after the last one skips the login.

`credentials.json`, `token.json`, `settings.json`, `reported.json` and `browser-profile/` are gitignored. Never commit them.
