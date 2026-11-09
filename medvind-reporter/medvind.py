import json
import time
from pathlib import Path

HERE = Path(__file__).parent
# a browser profile of its own, so your KTH login is remembered between runs
PROFILE = HERE / "browser-profile"
SESSION = PROFILE / "session-cookies.json"
START_URL = "https://kth.hrplus.visma.se/SeamlessMedvind?module=PERSONPERIOD"
MEDVIND_HOST = "medvind.visma.com"
LOGIN_TIMEOUT = 300

# Medvind has no public API, so this calls the same functions its own page uses when you open and save a day
CALL = """([module, func, params, xml, mask]) => new Promise(resolve => {
    const options = {
        noFocusRestore: true,
        result_success: response => resolve(response.responseText),
        result_failure: (response, _, message) => resolve(JSON.stringify(
            {mvresult: {success: false, message: message || (response && response.responseText) || "failed"}})),
    };
    if (xml) options.xmlData = Medvind.util.XmlWriter.GetJsonAsXml("dayinfo", null, xml);
    Medvind.util.Ajax.request_ModuleFunc(module, func, params, mask, "MyScope", options);
})"""
READY = "() => !!(window.Medvind && window.g_Workspace && g_Workspace.m_clActive && g_Workspace.m_clActive.focus.sPnr)"


class MedvindError(Exception):
    pass


BROWSERS = ["auto", "firefox", "chrome", "msedge", "chromium"]
# Windows' name for the default browser -> Playwright's
DEFAULTS = {"firefox": "firefox", "chrome": "chrome", "msedge": "msedge"}


def default_browser():
    # the browser Windows opens links in, e.g. "FirefoxURL-308046B0AF4A39CB" or "ChromeHTML"
    try:
        import winreg

        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice")
        prog_id = winreg.QueryValueEx(key, "ProgId")[0].lower()
    except (ImportError, OSError):
        return None
    return next((name for key, name in DEFAULTS.items() if prog_id.startswith(key)), None)


def auto_order():
    # your default browser first, then the others
    order = ["chrome", "msedge", "firefox", "chromium"]
    default = default_browser()
    return [default] + [b for b in order if b != default] if default else order


def launch(playwright, browser):
    # each browser gets its own profile folder, their profiles don't mix
    options = {"headless": False, "no_viewport": True}
    profile = str(PROFILE / browser)
    if browser == "firefox":
        # Playwright can't drive your installed Firefox, only its own build: python -m playwright install firefox
        return playwright.firefox.launch_persistent_context(profile, **options)
    # with the sandbox on, Playwright doesn't add --no-sandbox (which Edge and Chrome warn about)
    channel = None if browser == "chromium" else browser
    return playwright.chromium.launch_persistent_context(profile, channel=channel, chromium_sandbox=True, **options)


class Medvind:
    def __init__(self, browser="auto"):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise RuntimeError("Medvind needs: pip install -r requirements.txt")
        self.playwright = sync_playwright().start()
        errors = []
        for name in auto_order() if browser == "auto" else [browser]:
            try:
                self.context = launch(self.playwright, name)
                break
            except Exception as error:
                errors.append(f"{name}: {str(error).splitlines()[0]}")
        else:
            self.playwright.stop()
            raise MedvindError("couldn't start a browser, see 'Browsers' in the README\n  " + "\n  ".join(errors))
        # KTH's login only sets cookies that end with the browser, so they are kept here between runs
        if SESSION.exists():
            try:
                self.context.add_cookies(json.loads(SESSION.read_text(encoding="utf-8")))
            except Exception:
                pass  # broken or outdated, log in again
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        self.frame = None
        self.pnr = None

    def close(self):
        try:
            cookies = [c for c in self.context.cookies() if c.get("expires", -1) == -1]
            SESSION.write_text(json.dumps(cookies), encoding="utf-8")
        except Exception:
            pass  # the window was already closed
        try:
            self.context.close()
        except Exception:
            pass
        self.playwright.stop()

    def open(self):
        self.page.goto(START_URL)
        told = False
        on_login_since = None
        deadline = time.monotonic() + LOGIN_TIMEOUT
        while time.monotonic() < deadline:
            if self.page.is_closed():
                raise MedvindError("the browser window was closed before Medvind opened")
            for frame in self.page.frames:
                if MEDVIND_HOST in frame.url:
                    try:
                        if frame.evaluate(READY):
                            self.frame = frame
                            self.pnr = frame.evaluate("() => g_Workspace.m_clActive.focus.sPnr")
                            return
                    except Exception:
                        pass  # still loading, or navigating away
            url = self.page.url
            if "hrplus.visma.se" in url and "SeamlessMedvind" not in url and "LogOn" not in url:
                # logged in, but KTH-HR landed on its start page
                self.page.goto(START_URL)
            elif "login" in url and "kth.se" in url:
                # a remembered login only passes through KTH's login page, so wait a moment before asking
                on_login_since = on_login_since or time.monotonic()
                if not told and time.monotonic() - on_login_since > 4:
                    print("Log in to KTH in the browser window that opened (the session is kept for a while after).")
                    told = True
            try:
                self.page.wait_for_timeout(1000)
            except Exception:
                pass  # the window was closed, caught at the top of the loop
        raise MedvindError("Medvind didn't open, log in within 5 minutes and try again")

    def call(self, module, func, params, xml=None, mask=True):
        params = {"PNR": self.pnr, **params}
        text = self.frame.evaluate(CALL, [module, func, params, xml, mask])
        try:
            result = json.loads(text) if text else {}
        except json.JSONDecodeError:
            raise MedvindError(f"Unexpected answer from Medvind: {text[:300]}")
        status = result.get("mvresult", {})
        if status.get("success") is False:
            raise MedvindError(status.get("message") or status.get("msg") or text[:300])
        return result

    def load_day(self, day):
        # every placement's entry for that day, each with its intervals ("intv", start and end in minutes)
        result = self.call("PERSONPERIOD", "LOADDAY", {"DATE": day.isoformat()})
        person = next(iter(result["planperiod"]["personperiod"].values()))
        return person.get("arbtid", {}).get("D" + day.strftime("%Y%m%d"), [])

    def worked_days(self, placement, start, end):
        # the days that already have time on a placement
        result = self.call("PLANPERIOD", "PLAN_PERSON", {
            "ANSTNR": placement["anstnr"], "ORGID": placement["planid"], "PLANID": placement["planid"],
            "PERIODSTART": start.isoformat(), "PERIODEND": end.isoformat(),
            "CELLTYP": "G", "SHOW_OTHER": 0, "VIEW": "PLANPERSON",
        })
        days = []
        for week in result.get("kalender", []):
            for key, cell in week.get("time", {}).items():
                if cell.get("rows"):
                    days.append(f"{key[1:5]}-{key[5:7]}-{key[7:9]}")
        return sorted(days)

    def save_day(self, entry, day):
        # saving a day replaces all its intervals on that placement, so entry["intv"] must hold the old ones too
        self.call("PERSONPERIOD", "SAVEDAY", {
            "ANSTNR": entry["anstnr"], "PLANID": entry["planid"], "DATE": day.isoformat(),
            "PERIODSTART": day.isoformat(), "PERIODEND": day.isoformat(), "OUTPUT": "X", "MEMOTEXT": "null",
        }, xml=entry, mask=False)
