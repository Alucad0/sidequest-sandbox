# Medvind reporter

Reports the TA sessions in your **WORK** Google Calendar as worked hours in Medvind, KTH's time reporting (KTH-HR → Egenrapportering → Min arbetstid). The sessions are the ones the [schedule finder](../schedule-finder/) added.

Medvind has no API, so the program opens a browser window where you log in to KTH yourself. It never sees your password. Then it makes the same calls Medvind's own page makes when you open and save a day.

## Quick start

```bash
pip install -r requirements.txt
python medvind_reporter.py --dry-run
```

1. A Google sign-in may open first, to read your calendar.
2. A browser window opens KTH-HR. Log in to KTH there.
3. The first time, you pick your Medvind placement (see Setup).
4. You get a list of what would be reported. Nothing is saved in a dry run.

Run it again without `--dry-run` to report:

```bash
python medvind_reporter.py
```

```output
Reading WORK, 2026-10-01 to 2026-11-09
  16 events left out (not from the schedule finder, or marked with ?)
Opening Medvind

Avdelning Personal (ABC), Intermittent, Anstnr: 1234567:04  (Student(165), account ABC,123456,, 75 min prep)
   ✓ Wed 28 Oct  13:00-15:00  DD1310-Datorlaboration -> 11:45-15:00 3.25 h  already reported
   1 Wed 04 Nov  16:00-18:00  DD1310-Datorlaboration -> 14:45-18:00 3.25 h  DD1310-labb, CMATD/COPEN, 16-18
   2 Fri 06 Nov  13:00-14:00  DD1310-Övning      -> 11:45-14:00 2.25 h  DD1310-övn, TINTE, 13-14
   ✗ Mon 09 Nov  08:00-10:00  DD1310-Datorlaboration -> 06:45-10:00 3.25 h  not worked yet

Which do you want to report in Medvind? (e.g. 1 3 5-8, all, Enter for none): all

Reporting:
   1 Wed 04 Nov  16:00-18:00  DD1310-Datorlaboration -> 14:45-18:00 3.25 h  DD1310-labb, CMATD/COPEN, 16-18
   2 Fri 06 Nov  13:00-14:00  DD1310-Övning      -> 11:45-14:00 2.25 h  DD1310-övn, TINTE, 13-14
Reported 2 of 2 in Medvind, they still need your manager's approval
```

Each line shows the session in WORK, then `->` and what goes into Medvind.

| Mark | Meaning |
|---|---|
| `1`, `2`, … | can be reported, pick it by number |
| `✓` | already reported by this program |
| `✗` | won't be reported, the end of the line says why |

## Which events are listed

Only sessions with a schedule finder title like `DD1310-Övning`. Left out are:

- meetings and other events you typed in yourself,
- sessions marked as not confirmed with `?` in front (`? DD1310-Övning`).

A listed session can't be reported (`✗`) when:

| Reason | |
|---|---|
| `not worked yet` | it hasn't ended |
| `overlaps time already in Medvind` | you reported it by hand, or it clashes with another shift that day |
| `Låst, period (delvis) attesterad` | the day is locked, its period is approved |
| `placement not open that day` | your placement doesn't cover that day |
| `crosses midnight, report it by hand` | |

## What gets reported

| Field | Value |
|---|---|
| Time | labs and övningar get `--prep` minutes (default 75) before them, so a 2 h lab is 3.25 h. Other activities keep their own time. If two picked shifts would overlap, the later one is moved later and keeps its length. |
| Comment | course and activity, class, and the session's own hours: `DD1310-labb, CMATD/COPEN, 16-18`. The class comes from the description the schedule finder writes. |
| Time type, task, account | copied from a shift you reported by hand (see Setup) |
| Placement | the one you picked; ones marked **RAPPORTERA EJ TID HÄR** are never used |

**Never twice:** reported sessions are remembered in `reported.json`, and anything that overlaps time already in Medvind is skipped. After saving, each day is read back from Medvind to check the shifts are really there.

Reported time still needs your manager's approval in Medvind, like time you enter by hand.

## Options

| Option | |
|---|---|
| `--from`, `--to` | date range, `YYYY-MM-DD` (default the first day of last month to today) |
| `--dry-run` | show what would be reported without reporting it |
| `--prep MIN` | preparation minutes before each lab or övning (default 75) |
| `--calendar NAME` | calendar to read instead of `WORK` |
| `--browser NAME` | `auto` (default), `chrome`, `msedge`, `chromium` or `firefox`, see Browsers |
| `--setup` | pick the Medvind placement again |

## Setup

1. Install the packages:

   ```bash
   pip install -r requirements.txt
   ```

2. Copy `credentials.json` from the schedule finder folder, or follow the schedule finder's [Google Calendar setup](../schedule-finder/README.md#google-calendar-setup). This program only reads your calendar.

3. Report one shift by hand in Medvind on the placement you use. On the first run you pick that placement from a list, and its time type, task and account are copied from that shift into `settings.json`. Run with `--setup` to pick again.

## Browsers

The program uses [Playwright](https://playwright.dev/python/) to open a browser that you log in to, so it can work inside Medvind with your session.

| `--browser` | Uses | Needs |
|---|---|---|
| `auto` (default) | Chrome, else Edge, else Playwright's Chromium | nothing extra if Chrome or Edge is installed |
| `chrome` | your installed Google Chrome | Chrome |
| `msedge` | your installed Microsoft Edge | Edge (always there on Windows) |
| `chromium` | Playwright's own Chromium | `python -m playwright install chromium` |
| `firefox` | Playwright's own Firefox build, not your installed Firefox | `python -m playwright install firefox` |

Playwright can drive the Chrome and Edge you already have, but for Firefox it needs its own modified build. Each browser gets its own profile in `browser-profile/`, separate from your normal browsing.

KTH's login only lasts while the browser is open, so the program saves that session in `browser-profile/` when it closes. A run soon after the last one skips the login. Later on, KTH asks you to log in again.

## Troubleshooting

| Problem | Fix |
|---|---|
| `couldn't start a browser` | install Chrome or Edge, or run the `playwright install` command for the browser you picked |
| Google says "Something went wrong" when signing in | close old sign-in tabs and use the newest link, or open it in a private window |
| `Medvind didn't open` | log in within 5 minutes; if KTH-HR shows its start page, the program goes on to Min arbetstid by itself |
| `Report one shift on that placement by hand first` | enter one shift in Medvind yourself, then run again |
| A shift is reported but wrong | change or delete it in Medvind as usual, the program won't report that session again |

## Files

| File | |
|---|---|
| `medvind_reporter.py` | the program: reads WORK, lists, asks and reports |
| `medvind.py` | opens the browser and calls Medvind |
| `gcal.py` | Google sign-in and reading the calendar |
| `credentials.json`, `token.json` | your Google app and sign-in |
| `settings.json` | your placement, time type, task and account |
| `reported.json` | the sessions already reported |
| `browser-profile/` | the browser profiles and the saved KTH session |

All the files from `credentials.json` down are personal and gitignored. Never commit them.
