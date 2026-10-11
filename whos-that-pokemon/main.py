import difflib
import os
import random
import sys
import webbrowser
from urllib.error import URLError

import sprite
from pokemon import Pokemon, all_species, get_bytes, normalize, pretty

MAX_GUESSES = 5
YES = {"y", "ye", "yes", "yeah", "yep", "sure", "c", "cont", "continue", "play", ""}
QUIT = {"q", "quit", "exit"}
GIVE_UP = {"skip", "give up", "pass"}


def clear():
    # clear the terminal screen, should work on Windows and Linux/macOS
    print("\033[2J\033[H", end="")


def ask(prompt):
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        raise SystemExit(0)


def show_clues(mon, stage, guesses, png, score):
    clear()
    print(f"Who's that Pokémon?   score {score}   guess {stage}/{MAX_GUESSES}\n")

    # each wrong guess unlocks the next clue: 1 letters/gen/abilities, 2 types,
    # 3 index + first letter, 4 silhouette, 5 colour sprite
    print(f"Name:        {mon.name_hint(show_first=stage >= 3)}   ({mon.letter_count()} letters)")
    print(f"Generation:  {mon.generation}")
    print(f"Abilities:   {', '.join(mon.abilities)}")
    if stage >= 2:
        print(f"Type:        {' / '.join(mon.types)}")
    if stage >= 3:
        print(f"Index:       #{mon.index}")
    if guesses:
        print(f"Guessed:     {', '.join(guesses)}")

    if stage >= 4 and png:
        if sprite.can_render():
            print()
            print(sprite.render(png, silhouette=stage == 4))
        elif stage == 5:
            # without Pillow the sprite can only be shown in the browser
            webbrowser.open(mon.sprite_url)
            print("\n(Sprite opened in your browser)")


def suggestion(guess, names):
    close = difflib.get_close_matches(normalize(guess), names, n=1, cutoff=0.7)
    return f" Did you mean {names[close[0]]}?" if close else ""


def play_round(mon, names, score):
    # downloaded up front so the silhouette and colour clues show without a pause
    png = None
    if mon.sprite_url:
        try:
            png = get_bytes(mon.sprite_url)
        except URLError:
            pass

    guesses = []
    message = ""
    while len(guesses) < MAX_GUESSES:
        stage = len(guesses) + 1
        show_clues(mon, stage, guesses, png, score)
        if message:
            print(f"\n{message}")
        guess = ask("\nYour guess: ")
        message = ""

        if not guess:
            continue
        if guess.lower() in QUIT:
            raise SystemExit(0)
        if guess.lower() in GIVE_UP:
            break
        if mon.matches(guess):
            points = MAX_GUESSES + 1 - stage
            show_clues(mon, MAX_GUESSES, guesses, png, score)
            print(f"\nThat's right, it's {mon.name}! +{points} points")
            return points
        # guesses that aren't Pokémon names don't cost a clue
        if normalize(guess) not in names:
            message = f"'{guess}' isn't a Pokémon.{suggestion(guess, names)}"
            continue
        guesses.append(names[normalize(guess)])

    show_clues(mon, MAX_GUESSES, guesses, png, score)
    print(f"\nIt was {mon.name}!")
    return 0


def main():
    # lets Windows consoles understand the colour codes and print the half-block characters
    os.system("")
    sys.stdout.reconfigure(encoding="utf-8")

    try:
        species = all_species()
    except URLError as error:
        print(f"Couldn't reach PokéAPI ({error.reason}). Check your connection and try again.")
        return
    names = {normalize(slug): pretty(slug) for slug in species}
    # the API calls them nidoran-f and nidoran-m, but players will just type "nidoran"
    names["nidoran"] = "Nidoran"

    print('This is "Who\'s that Pokémon?"')
    print("Type a name to guess, 'skip' to give up on a Pokémon, or 'quit' to stop.")
    if not sprite.can_render():
        print("Tip: run 'pip install pillow' to see the sprites in the terminal.")
    if ask("\nReady to play? [Y/n] ").lower() not in YES:
        return

    score = 0
    rounds = 0
    while True:
        try:
            mon = Pokemon.fetch(random.randint(1, len(species)))
        except URLError as error:
            print(f"Couldn't load a Pokémon ({error.reason}).")
            if ask("Try again? [Y/n] ").lower() not in YES:
                break
            continue

        rounds += 1
        score += play_round(mon, names, score)
        if ask("\nPlay another? [Y/n] ").lower() not in YES:
            break

    print(f"\nFinal score: {score} from {rounds} Pokémon. Thanks for playing!")


if __name__ == "__main__":
    main()
