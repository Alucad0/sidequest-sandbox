import io
import math
import queue
import random
import textwrap
import threading
import tkinter as tk
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageTk

from main import MAX_GUESSES, suggestion
from pokemon import Pokemon, all_species, get_bytes, normalize, pretty

W, H = 960, 640
SCREEN_X, SCREEN_Y, SCREEN_W, SCREEN_H = 80, 165, 380, 240
SPRITE_MAX_W, SPRITE_MAX_H = 300, 190

RED = "#dc0a2d"
RED_EDGE = "#7a0016"
LCD = "#9bbc0f"
LCD_TEXT = "#0f380f"
BLUE = "#2a75bb"
SILHOUETTE = (14, 22, 48)

# Luckiest Guy by Astigmatic, Apache License 2.0 (see fonts/LICENSE.txt)
FONT_FILE = Path(__file__).parent / "fonts" / "LuckiestGuy-Regular.ttf"

# (gradient top, gradient bottom, outline, shadow)
TITLE_STYLE = ((255, 236, 90), (255, 168, 0), (34, 70, 170), (8, 20, 70))
GUESS_STYLE = ((255, 255, 255), (205, 230, 255), (20, 60, 110), None)
WHITE_BUTTON_STYLE = ((255, 85, 95), (200, 10, 45), (90, 0, 20), None)
LCD_FONT = ("Consolas", 12)
NAME_FONT = ("Consolas", 20, "bold")


def styled_text(text, size, style, max_width=None):
    # renders text in Luckiest Guy with a vertical gradient, a thick outline and a drop shadow
    top, bottom, outline, shadow = style
    # the font is all capitals, but its lowercase "é" is small, so use real capitals
    text = text.upper()
    font = ImageFont.truetype(str(FONT_FILE), size)
    stroke = max(2, size // 9)
    while max_width and font.getlength(text) + 2 * stroke > max_width and size > 12:
        size -= 2
        font = ImageFont.truetype(str(FONT_FILE), size)
        stroke = max(2, size // 9)

    drop = max(2, size // 10) if shadow else 0
    left, upper, right, lower = font.getbbox(text, stroke_width=stroke)
    w, h = right - left, lower - upper + drop
    origin = (-left, -upper)
    image = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(image)
    if shadow:
        d.text((origin[0], origin[1] + drop), text, font=font, fill=shadow, stroke_width=stroke, stroke_fill=shadow)
    d.text(origin, text, font=font, fill=outline, stroke_width=stroke, stroke_fill=outline)

    # top-to-bottom gradient, only where the letters are
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).text(origin, text, font=font, fill=255)
    gradient = Image.new("RGBA", (1, h))
    for y in range(h):
        t = y / max(1, h - drop - 1)
        t = min(1, t)
        gradient.putpixel((0, y), tuple(round(a + (b - a) * t) for a, b in zip(top, bottom)) + (255,))
    image.paste(gradient.resize((w, h)), (0, 0), mask)
    return image


def draw_device():
    # drawn at twice the size and scaled down so the curves are smooth
    s = 2
    image = Image.new("RGBA", (W * s, H * s), (0, 0, 0, 0))
    d = ImageDraw.Draw(image)

    def box(x0, y0, x1, y1, radius, fill, outline=None, width=0):
        d.rounded_rectangle((x0 * s, y0 * s, x1 * s, y1 * s), radius * s, fill=fill, outline=outline, width=width * s)

    def circle(x, y, r, fill, outline=None, width=0):
        d.ellipse(((x - r) * s, (y - r) * s, (x + r) * s, (y + r) * s), fill=fill, outline=outline, width=width * s)

    # the two halves of the Pokédex and the hinge between them
    box(20, 20, 520, 620, 28, RED, RED_EDGE, 3)
    box(540, 20, 940, 620, 28, RED, RED_EDGE, 3)
    box(512, 70, 548, 570, 10, "#a8001f", RED_EDGE, 2)
    d.line([(20 * s, 125 * s), (270 * s, 125 * s), (310 * s, 95 * s), (520 * s, 95 * s)], fill=RED_EDGE, width=3 * s)
    d.line([(540 * s, 95 * s), (940 * s, 95 * s)], fill=RED_EDGE, width=3 * s)

    # big blue lens and the three status lights
    circle(78, 70, 40, "white", "#333333", 3)
    circle(78, 70, 30, "#3fa9f5", "#1b4f80", 2)
    circle(68, 60, 9, "#bfe6ff")
    for x, colour in ((150, "#ff3b3b"), (180, "#ffd93b"), (210, "#3bd16f")):
        circle(x, 45, 9, colour, "#333333", 2)

    # screen bezel
    box(50, 135, 490, 440, 14, "#dedede", "#333333", 2)
    circle(250, 150, 5, "#ff2a2a")
    circle(270, 150, 5, "#ff2a2a")
    box(SCREEN_X - 3, SCREEN_Y - 3, SCREEN_X + SCREEN_W + 3, SCREEN_Y + SCREEN_H + 3, 6, "#222222")
    circle(78, 423, 9, "#ff2a2a", "#333333", 2)
    for y in (416, 421, 426, 431):
        d.line([(420 * s, y * s), (470 * s, y * s)], fill="#333333", width=2 * s)

    # name display, text box and guess button
    box(50, 455, 490, 505, 8, LCD, "#333333", 2)
    box(50, 525, 330, 575, 8, "white", "#333333", 2)
    box(345, 525, 490, 575, 10, BLUE, "#1b4f80", 2)

    # clue screen, message bar and the two white buttons
    box(565, 120, 915, 400, 12, "#dedede", "#333333", 2)
    box(578, 132, 902, 388, 6, LCD, "#333333", 2)
    box(565, 470, 915, 520, 8, "#222222", "#111111", 2)
    box(565, 545, 730, 590, 10, "white", "#333333", 2)
    box(750, 545, 915, 590, 10, "white", "#333333", 2)

    return image.resize((W, H), Image.LANCZOS)


def draw_rays():
    # the blue light-burst background from the anime
    s = 2
    w, h = SCREEN_W * s, SCREEN_H * s
    cx, cy = w * 0.5, h * 0.55
    image = Image.new("RGB", (w, h), (40, 90, 200))
    d = ImageDraw.Draw(image)
    rays = 28
    for i in range(rays):
        a0 = 2 * math.pi * i / rays
        a1 = 2 * math.pi * (i + 0.5) / rays
        far = max(w, h) * 1.5
        points = [(cx, cy), (cx + far * math.cos(a0), cy + far * math.sin(a0)), (cx + far * math.cos(a1), cy + far * math.sin(a1))]
        d.polygon(points, fill=(95, 160, 245))

    glow = Image.new("L", (w, h), 0)
    ImageDraw.Draw(glow).ellipse((cx - 170, cy - 130, cx + 170, cy + 130), fill=255)
    glow = glow.filter(ImageFilter.GaussianBlur(70))
    image = Image.composite(Image.new("RGB", (w, h), (225, 245, 255)), image, glow)
    return image.resize((SCREEN_W, SCREEN_H), Image.LANCZOS)


def prepare_sprite(png):
    # crops the empty border and scales the pixel art up without blurring it
    sprite = Image.open(io.BytesIO(png)).convert("RGBA")
    bbox = sprite.getchannel("A").getbbox()
    if bbox:
        sprite = sprite.crop(bbox)
    scale = max(1, min(SPRITE_MAX_W // sprite.width, SPRITE_MAX_H // sprite.height))
    sprite = sprite.resize((sprite.width * scale, sprite.height * scale), Image.NEAREST)

    mask = sprite.getchannel("A").point(lambda a: 255 if a >= 128 else 0)
    silhouette = Image.new("RGBA", sprite.size, SILHOUETTE + (255,))
    silhouette.putalpha(mask)
    return sprite, silhouette


class Game:
    def __init__(self, root):
        self.root = root
        self.results = queue.Queue()
        self.names = {}
        self.species_count = 0
        self.score = 0
        self.mon = None
        self.sprite = None
        self.silhouette = None
        self.guesses = []
        self.over = False
        self.loading = False

        root.title("Who's that Pokémon?")
        root.resizable(False, False)
        self.canvas = tk.Canvas(root, width=W, height=H, bg="#1e1e1e", highlightthickness=0)
        self.canvas.pack()

        self.device = ImageTk.PhotoImage(draw_device())
        self.rays = draw_rays()
        self.canvas.create_image(0, 0, image=self.device, anchor="nw")
        self.screen = self.canvas.create_image(SCREEN_X, SCREEN_Y, anchor="nw")

        self.name_text = self.canvas.create_text(270, 480, font=NAME_FONT, fill=LCD_TEXT)
        self.clue_text = self.canvas.create_text(592, 145, font=LCD_FONT, fill=LCD_TEXT, anchor="nw")
        self.message = self.canvas.create_text(740, 495, font=("Segoe UI", 11), fill="white", width=330)

        self.entry = tk.Entry(root, font=("Segoe UI", 16), relief="flat", bd=0)
        self.canvas.create_window(62, 550, window=self.entry, anchor="w", width=258, height=34)
        self.entry.bind("<Return>", lambda e: self.next_round() if self.over else self.guess())
        self.entry.focus_set()

        self.text_images = {}
        self.buttons = []
        self.button((345, 525, 490, 575), "GUESS", GUESS_STYLE, self.guess)
        self.button((565, 545, 730, 590), "SKIP", WHITE_BUTTON_STYLE, self.skip)
        self.button((750, 545, 915, 590), "NEXT", WHITE_BUTTON_STYLE, self.next_round)
        self.canvas.bind("<Button-1>", self.click)
        self.canvas.bind("<Motion>", self.hover)

        self.keys = []
        for i in range(MAX_GUESSES):
            x = 575 + i * 68
            self.keys.append(self.canvas.create_rectangle(x, 415, x + 58, 450, outline="#1b4f80", width=2))

        self.show_message("Connecting to PokéAPI…")
        self.render()
        self.run_async(all_species, self.species_loaded)
        self.poll()

    def button(self, area, label, style, command):
        # the button shapes are part of the device image, so clicks are matched by position
        self.buttons.append((area, command))
        x0, y0, x1, y1 = area
        self.place_text((x0 + x1) // 2, (y0 + y1) // 2 + 2, label, 22, style, f"button_{label}")

    def button_at(self, x, y):
        for (x0, y0, x1, y1), command in self.buttons:
            if x0 <= x <= x1 and y0 <= y <= y1:
                return command

    def click(self, event):
        command = self.button_at(event.x, event.y)
        if command:
            command()

    def hover(self, event):
        self.canvas.config(cursor="hand2" if self.button_at(event.x, event.y) else "")

    def place_text(self, x, y, text, size, style, tag, max_width=None):
        self.canvas.delete(tag)
        self.text_images[tag] = ImageTk.PhotoImage(styled_text(text, size, style, max_width))
        self.canvas.create_image(x, y, image=self.text_images[tag], tags=tag)

    # network calls run on a thread so the window doesn't freeze; results come back through the queue
    def run_async(self, work, callback):
        def worker():
            try:
                self.results.put((callback, work(), None))
            except Exception as error:
                self.results.put((callback, None, error))
        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        while not self.results.empty():
            callback, result, error = self.results.get()
            callback(result, error)
        self.root.after(50, self.poll)

    def species_loaded(self, species, error):
        if error:
            self.show_message(f"Couldn't reach PokéAPI ({error}). Restart to try again.")
            return
        self.names = {normalize(slug): pretty(slug) for slug in species}
        # the API calls them nidoran-f and nidoran-m, but players will just type "nidoran"
        self.names["nidoran"] = "Nidoran"
        self.species_count = len(species)
        self.next_round()

    def next_round(self):
        if not self.species_count or self.loading or (self.mon and not self.over):
            return
        self.loading = True
        self.over = False
        self.guesses = []
        self.mon = None
        self.sprite = self.silhouette = None
        self.show_message("Loading a Pokémon…")
        self.render()

        def load():
            mon = Pokemon.fetch(random.randint(1, self.species_count))
            png = get_bytes(mon.sprite_url) if mon.sprite_url else None
            return mon, png
        self.run_async(load, self.round_loaded)

    def round_loaded(self, result, error):
        self.loading = False
        if error:
            self.show_message(f"Couldn't load a Pokémon ({error}). Press NEXT to try again.")
            self.over = True
            return
        self.mon, png = result
        if png:
            self.sprite, self.silhouette = prepare_sprite(png)
        self.show_message("Type your guess and press Enter.")
        self.render()

    def stage(self):
        return MAX_GUESSES if self.over else len(self.guesses) + 1

    def guess(self):
        text = self.entry.get().strip()
        if self.over or self.loading or not self.mon or not text:
            return
        self.entry.delete(0, "end")

        if self.mon.matches(text):
            points = MAX_GUESSES + 1 - self.stage()
            self.score += points
            self.finish(f"It's {self.mon.name}!", f"Correct! +{points} points. Press Enter for the next one.")
            return
        # guesses that aren't Pokémon names don't cost a clue
        if normalize(text) not in self.names:
            self.show_message(f"'{text}' isn't a Pokémon.{suggestion(text, self.names)}")
            return

        self.guesses.append(self.names[normalize(text)])
        if len(self.guesses) >= MAX_GUESSES:
            self.finish(f"It's {self.mon.name}!", "Out of guesses. Press Enter for the next one.")
        else:
            self.show_message(f"Not {self.guesses[-1]}. Here's another clue.")
            self.render()

    def skip(self):
        if self.mon and not self.over and not self.loading:
            self.finish(f"It's {self.mon.name}!", "Skipped. Press Enter for the next one.")

    def finish(self, reveal, message):
        self.over = True
        self.show_message(message)
        self.render(reveal)

    def show_message(self, text):
        self.canvas.itemconfig(self.message, text=text)

    def render(self, reveal=None):
        stage = self.stage()
        mon = self.mon

        # screen: light burst, then a silhouette on guess 4 and the colour sprite on guess 5 or when revealed
        frame = self.rays.copy()
        shown = None
        if self.sprite and (self.over or stage >= 5):
            shown = self.sprite
        elif self.silhouette and stage >= 4:
            shown = self.silhouette
        if shown:
            x = (SCREEN_W - shown.width) // 2
            y = 30 + (SCREEN_H - 30 - shown.height) // 2
            frame.paste(shown, (x, y), shown)
        self.frame = ImageTk.PhotoImage(frame)
        self.canvas.itemconfig(self.screen, image=self.frame)

        if "title" not in self.text_images:
            self.place_text(SCREEN_X + SCREEN_W // 2, SCREEN_Y + 24, "Who's that Pokémon?", 32, TITLE_STYLE, "title")
        self.canvas.delete("mystery", "reveal")
        if mon and not shown:
            self.place_text(SCREEN_X + SCREEN_W // 2, SCREEN_Y + 140, "?", 120, TITLE_STYLE, "mystery")
        if reveal:
            self.place_text(SCREEN_X + SCREEN_W // 2, SCREEN_Y + SCREEN_H - 26, reveal, 34, TITLE_STYLE, "reveal", SCREEN_W - 20)

        # name display: blanks per letter, first letter from guess 3
        name = (mon.name if self.over else mon.name_hint(show_first=stage >= 3)) if mon else "…"
        self.canvas.itemconfig(self.name_text, text=name)

        # clue screen
        lines = [f"SCORE {self.score:<8}" + (f"No.{mon.index:04}" if mon and stage >= 3 else "No.????"), ""]
        if mon:
            lines.append(f"LETTERS  {mon.letter_count()}")
            lines.append(f"GEN      {mon.generation}")
            lines.append("TYPE     " + (" / ".join(mon.types) if stage >= 2 else "???"))
            lines += textwrap.wrap(", ".join(mon.abilities), 33, initial_indent="ABILITY  ", subsequent_indent=" " * 9)
            if self.guesses:
                lines.append("")
                lines += textwrap.wrap(", ".join(self.guesses), 33, initial_indent="GUESSED  ", subsequent_indent=" " * 9)
        self.canvas.itemconfig(self.clue_text, text="\n".join(lines))

        # the blue keys light up as guesses are used
        for i, key in enumerate(self.keys):
            used = i < len(self.guesses)
            self.canvas.itemconfig(key, fill="#9fd3ff" if used else BLUE)


def main():
    root = tk.Tk()
    Game(root)
    root.mainloop()


if __name__ == "__main__":
    main()
