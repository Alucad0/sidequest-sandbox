# Schedule finder

Finds the labs and övningar you can TA without missing anything in the courses you take, and adds the ones you pick to your Google Calendar.

Schedules come from KTH's public [TimeEdit](https://cloud.timeedit.net/kth/web/public01/). Before listing anything, it also reads your **WORK** calendar, so nothing gets double-booked. The [Medvind reporter](../medvind-reporter/) can later report the sessions you added as worked hours.

## Quick start

```bash
pip install -r requirements.txt
python schedule_finder.py
```

Without arguments it asks for everything:

1. **Taking:** the courses you take, e.g. `SK1104 SF1672:CTFYS1,"grupp C"`.
2. **Schedule link:** your personal TimeEdit link, if you have one (Enter to skip).
3. **Teaching:** the courses you TA, one spec per class, e.g. `DD1310:COPEN+CMATD DD1310:TINTE`.
4. **Activities:** for each class, which activity types you teach, picked from what the class actually has.

You can also give it all at once:

```bash
python schedule_finder.py --taking SK1104 SF1672:CTFYS1,"grupp C" --teaching DD1310:COPEN+CMATD@datorlab DD1310:TINTE@datorlab/övning
```

```output
DD1310, Programming Techniques [COPEN+CMATD@datorlab or TINTE@datorlab/övning]
  Week 44
    ★ Wed 28 Oct 13:00-15:00  Datorlaboration Helklass (TINTE1)   already booked
    ✗ Thu 29 Oct 15:00-17:00  Övning          grupp A-B (TINTE1)   clashes with SK1104 Föreläsning (Helklass) 15:00
    1 Fri 30 Oct 08:00-10:00  Övning          grupp C-D (TINTE1)

Which sessions do you want in WORK? (e.g. 1 3 5-8, all, Enter for none): 1
Added 1 sessions to WORK
```

| Mark | Meaning |
|---|---|
| `1`, `2`, … | fits your schedule, pick it by number |
| `★` | already in WORK |
| `✗` | clashes with a course you take or something in WORK, and says with what |

## What ends up in WORK

- **Title:** course and activity, e.g. `DD1310-Övning`.
- **Time and room:** from TimeEdit.
- **Description:** group, programme (class), course offering and teacher, one per line.
- **Event id:** `timeedit<id>`, so picking a session twice updates it instead of duplicating it.

The Medvind reporter relies on this title and description. To mark a session as not confirmed yet, put `?` in front of its title in Google Calendar (`? DD1310-Övning`), and the reporter skips it.

## Course specs

`CODE[:FILTERS][@ACTIVITIES]`

| Spec | Meaning |
|---|---|
| `SK1104` | the whole course |
| `SF1672:CTFYS1,"grupp C"` | one programme, and only group C's övningar (also matches `grupp A-D`) |
| `DD1310:COPEN+CMATD` | sessions for both COPEN and CMATD (`+` = `,` = and) |
| `DD1310:COPEN DD1310:TINTE` | repeating a course means **or** |
| `DD1310:TINTE@datorlab/övning` | only those activity types (the start of the name is enough) |

Put a spec in quotes when it has a space, like `"grupp C"`. `ovning` and `övning` both work.

## Options

| Option | |
|---|---|
| `--taking SPEC …` | courses you take, their sessions count as busy |
| `--teaching SPEC …` | courses you TA, their sessions are listed |
| `--link URL …` | your personal TimeEdit link (`.ics` or `.html`), counted as busy |
| `--from`, `--to` | date range, `YYYY-MM-DD` (default today to the end of the term) |
| `--buffer MIN` | minutes needed between sessions, e.g. to change campus |
| `--activities …` | default activity types (`Laboration Datorlaboration Övning`) |
| `--free-only` | hide sessions that clash or are already booked |
| `--calendar NAME` | calendar to use instead of `WORK` |
| `--dry-run` | show what would be added without adding it |
| `--no-calendar` | don't use Google Calendar at all, only list sessions |

## Google Calendar setup

Needed once, unless you only use `--no-calendar`.

1. In [Google Cloud Console](https://console.cloud.google.com/), set up a project:
   - Enable the **Google Calendar API**.
   - Under **Google Auth Platform**, set up an **External** app and add your own Google account as a **test user**.
   - Create a **Desktop app** client and save its JSON in this folder as `credentials.json`.
2. Run the program. A browser window asks you to sign in. Google warns that the app is unverified; click **Continue**.

The sign-in is saved in `token.json`. While the app is in testing mode, Google asks again about once a week.

## Troubleshooting

| Problem | Fix |
|---|---|
| `Missing credentials.json` | do the Google Calendar setup above |
| Google says "Something went wrong" when signing in | close old sign-in tabs and use the newest link, or open it in a private window with only one Google account |
| `No calendar called WORK` | create the calendar in Google Calendar, or use `--calendar` |
| `Couldn't reach TimeEdit` | check your connection, TimeEdit is sometimes down for a while |

## Files

| File | |
|---|---|
| `schedule_finder.py` | the program: arguments, picking and listing |
| `timeedit.py` | reads courses and schedules from TimeEdit |
| `gcal.py` | Google sign-in, reading and adding events |
| `credentials.json`, `token.json` | your Google app and sign-in, gitignored. Never commit them. |
