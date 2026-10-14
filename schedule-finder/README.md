# Schedule finder

Finds labs and övningar you can TA without missing anything in the courses you take, and adds the ones you pick to your Google Calendar.

Schedules come from KTH's public [TimeEdit](https://cloud.timeedit.net/kth/web/public01/). Before listing anything, it also reads your **WORK** calendar so nothing gets double-booked.

## Usage

```bash
python schedule_finder.py --taking SK1104 SF1672:CTFYS1,"grupp C" --teaching DD1310:COPEN+CMATD@datorlab DD1310:TINTE@datorlab/övning
```

Run it without arguments to be asked instead. Then it also asks which activities you teach for each class.

```output
DD1310, Programming Techniques [COPEN+CMATD@datorlab or TINTE@datorlab/övning]
  Week 44
    ★ Wed 28 Oct 13:00-15:00  Datorlaboration Helklass (TINTE1)   already booked
    ✗ Thu 29 Oct 15:00-17:00  Övning          grupp A-B (TINTE1)   clashes with SK1104 Föreläsning (Helklass) 15:00
    1 Fri 30 Oct 08:00-10:00  Övning          grupp C-D (TINTE1)

Which sessions do you want in WORK? (e.g. 1 3 5-8, all, Enter for none): 1
Added 1 sessions to WORK
```

The picked sessions are added to WORK:

- **Title:** e.g. `DD1310-Övning`.
- **Time and room:** from TimeEdit.
- **Description:** group, programme, offering and teacher.

Picking a session twice updates it instead of duplicating it.

## Course specs

`CODE[:FILTERS][@ACTIVITIES]`

| Spec | Meaning |
|---|---|
| `SK1104` | the whole course |
| `SF1672:CTFYS1,"grupp C"` | one programme, and only group C's övningar (also matches `grupp A-D`) |
| `DD1310:COPEN+CMATD` | sessions for both COPEN and CMATD (`+` = `,` = and) |
| `DD1310:COPEN DD1310:TINTE` | repeating a course means **or** |
| `DD1310:TINTE@datorlab/övning` | only those activity types (the start of the name is enough) |

## Options

| Option | |
|---|---|
| `--link URL` | your personal TimeEdit link, counted as busy |
| `--from`, `--to` | date range, `YYYY-MM-DD` (default today to the end of the term) |
| `--buffer MIN` | minutes needed between sessions |
| `--activities …` | default activity types (`Laboration Datorlaboration Övning`) |
| `--free-only` | hide sessions that clash or are already booked |
| `--calendar NAME` | calendar to use instead of `WORK` |
| `--dry-run` | show what would be added without adding it |
| `--no-calendar` | don't use Google Calendar at all |

## Google Calendar setup

1. Install the packages:

   ```bash
   pip install -r requirements.txt
   ```

2. In [Google Cloud Console](https://console.cloud.google.com/), set up a project:
   - Enable the **Google Calendar API**.
   - Under **Google Auth Platform**, set up an **External** app and add your Gmail as a **test user**.
   - Create a **Desktop app** client and save its JSON here as `credentials.json`.

On the first run, a browser window asks you to sign in. Google warns that the app is unverified; click **Continue**. In testing mode this repeats about once a week.

`credentials.json` and `token.json` are gitignored. Never commit them.
