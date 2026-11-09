# Schedule finder

Finds labs and övningar you can TA without missing your own courses, and adds the ones you pick to your **WORK** Google Calendar.

Schedules come from KTH's public [TimeEdit](https://cloud.timeedit.net/kth/web/public01/). Your WORK calendar counts as busy too, so nothing gets double-booked.

## Usage

```bash
pip install -r requirements.txt
python schedule_finder.py
```

It asks for the courses you take, the ones you teach, and which activities you teach in each class. Or give it all at once:

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

`★` = already in WORK, `✗` = clashes, numbers = free to pick.

Picked sessions get the title `DD1310-Övning`, TimeEdit's time and room, and the group and class in the description. Picking one twice updates it. The [Medvind reporter](../medvind-reporter/) reports them as worked hours later; put `?` in front of a title if it isn't confirmed yet.

## Course specs

`CODE[:FILTERS][@ACTIVITIES]`

| Spec | Meaning |
|---|---|
| `SK1104` | the whole course |
| `SF1672:CTFYS1,"grupp C"` | one class, and only group C (also matches `grupp A-D`) |
| `DD1310:COPEN+CMATD` | both COPEN and CMATD |
| `DD1310:COPEN DD1310:TINTE` | COPEN or TINTE |
| `DD1310:TINTE@datorlab/övning` | only those activities |

## Options

| Option | |
|---|---|
| `--taking`, `--teaching` | course specs, see above |
| `--link URL` | your personal TimeEdit link, counted as busy |
| `--from`, `--to` | dates, `YYYY-MM-DD` (default today to the end of the term) |
| `--buffer MIN` | minutes needed between sessions |
| `--free-only` | hide sessions that clash or are booked |
| `--calendar NAME` | calendar instead of `WORK` |
| `--dry-run` | show what would be added |
| `--no-calendar` | don't use Google Calendar |

## Google Calendar setup

1. In [Google Cloud Console](https://console.cloud.google.com/), make a project, enable the **Google Calendar API**, and under **Google Auth Platform** set up an **External** app with your Google account as **test user**.
2. Create a **Desktop app** client and save its JSON here as `credentials.json`.
3. On the first run, sign in in the browser and click **Continue** past the "unverified app" warning. Google asks again about once a week.

If Google says "Something went wrong", close old sign-in tabs and use the newest link.

`credentials.json` and `token.json` are personal and gitignored.
