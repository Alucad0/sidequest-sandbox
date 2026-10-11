# Who's that Pokémon?

A terminal guessing game built on [PokéAPI](https://pokeapi.co/). A random Pokémon is picked from every generation, and each wrong guess unlocks another clue.

This started as a school project in its own repository, `Pokemon_api`, which was actively developed until the game was finished in February 2022. That repository was then archived. In 2026 the project moved here to sidequest-sandbox, where it was rewritten and given a Pokédex GUI.

## Clues

| Guess | New clue |
|------:|----------|
| 1 | Number of letters, generation, abilities |
| 2 | Type |
| 3 | Pokédex number and first letter |
| 4 | Silhouette of the sprite |
| 5 | The sprite in colour |

Getting it on guess 1 is worth 5 points, on guess 5 it's worth 1. Names that aren't Pokémon don't cost a guess, and typos get a "Did you mean …?". Capitals, spaces and punctuation are ignored, so `mr mime` counts for Mr. Mime.

Type `skip` to give up on a Pokémon or `quit` to stop.

## Running it

Needs Python 3.10+ and an internet connection.

```bash
pip install -r requirements.txt
```

### Pokédex GUI

```bash
python gui.py
```

A Pokédex window with the anime's "Who's that Pokémon?" screen: blue light burst, silhouette, then the reveal. The blue keys light up as you use guesses. Needs [Pillow](https://pypi.org/project/pillow/).

### Terminal

```bash
python main.py
```

Pillow is optional here. It draws the sprites in the terminal. Without it the game still runs, skips the silhouette and opens the colour sprite in your browser. Use a terminal with true colour, such as Windows Terminal or VS Code.

## License

[MIT](LICENSE.md). The bundled font [Luckiest Guy](https://fonts.google.com/specimen/Luckiest+Guy) by Astigmatic is under the [Apache License 2.0](fonts/LICENSE.txt).
