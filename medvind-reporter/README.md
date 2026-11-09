# Medvind reporter

Reports the TA sessions in your **WORK** Google Calendar as worked hours in Medvind (KTH-HR → Egenrapportering → Min arbetstid). The sessions come from the [schedule finder](../schedule-finder/).

Medvind has no API, so the program opens your browser and you log in to KTH yourself. It never sees your password.

## Usage

```bash
pip install -r requirements.txt
python medvind_reporter.py --dry-run
```

`--dry-run` only shows what would be reported. Without it, you pick what to report:

```output
Avdelning Personal (ABC), Intermittent, Anstnr: 1234567:04  (Student(165), account ABC,123456,, factor 1.8, övning 2)
   ✓ Wed 28 Oct  13:00-15:00  DD1310-Datorlaboration -> 11:45-15:00 3.25 h  already reported
   1 Wed 04 Nov  08:00-10:00  DD1310-Datorlaboration -> 06:15-10:00 3.75 h  DD1310-labb, CMATD/COPEN, 8-10, 2h*1.8=3.6h up to 3.75h
   2 Fri 06 Nov  13:00-14:00  DD1310-Övning      -> 12:30-14:00 1.50 h  DD1310-övn, TINTE, 13-14, 0.75h*2=1.5h
   ✗ Mon 09 Nov  10:00-12:00  DD1310-Datorlaboration -> 08:45-12:00 3.25 h  not worked yet

Which do you want to report in Medvind? (e.g. 1 3 5-8, all, Enter for none): all
Reported 2 of 2 in Medvind, they still need your manager's approval
```

`✓` = already reported, `✗` = can't be reported (the line says why), numbers = can be picked.

## How hours are counted

1. **Worked time:** sessions start a quarter past, so 10–12 is 1.75 h. Sessions at 8:00 start on the hour, so 8–10 is 2 h.
2. **Times the schablonfaktor:** 2 for övningar, 1.8 for labs and the rest.
3. **Rounded UP** to the nearest 15 minutes.

| Session | Calculation | Reported |
|---|---|---|
| lab 8–10 | 2h × 1.8 = 3.6h, up to 3.75h | 06:15–10:00 |
| lab 10–12 | 1.75h × 1.8 = 3.15h, up to 3.25h | 08:45–12:00 |
| övning 13–14 | 0.75h × 2 = 1.5h | 12:30–14:00 |

The shift ends when the session ends. If that time is already taken in Medvind, by planning on any placement or another shift, it's moved later to the first free quarter hour, e.g. past the daily 08:00–08:24 planning. The comment in Medvind shows the session and the calculation:

`DD1310-labb, CMATD/COPEN, 8-10, 2h*1.8=3.6h up to 3.75h`

## What is skipped

- Events that aren't from the schedule finder, like meetings.
- Sessions with `?` in front of the title (not confirmed).
- Sessions already reported (kept in `reported.json`), or reported by hand (a shift on your placement during the session).
- Sessions that haven't ended, and days in a locked period.

## Options

| Option | |
|---|---|
| `--from`, `--to` | dates, `YYYY-MM-DD` (default the 1st of last month to today) |
| `--dry-run` | only show what would be reported |
| `--factor`, `--factor-ovning` | schablonfaktor for labs (1.8) and övningar (2) |
| `--calendar` | calendar to read (default `WORK`) |
| `--browser` | `auto`, `firefox`, `chrome`, `msedge` or `chromium` |
| `--setup` | pick the Medvind placement again |

## Setup

1. Copy `credentials.json` from the schedule finder (see its [Google Calendar setup](../schedule-finder/README.md#google-calendar-setup)).
2. Report one shift by hand in Medvind. On the first run you pick that placement, and its time type and account are copied. Placements marked **RAPPORTERA EJ TID HÄR** are never used.

## Browser

`auto` uses your default browser, then Chrome, Edge or Playwright's Chromium. Chrome and Edge work as they are. Firefox needs Playwright's own copy, installed once:

```bash
python -m playwright install firefox
```

Your KTH login is kept for a while, so runs close together don't ask again.

`credentials.json`, `token.json`, `settings.json`, `reported.json` and `browser-profile/` are personal and gitignored.
