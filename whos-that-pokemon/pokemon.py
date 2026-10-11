from __future__ import annotations

import json
import unicodedata
import urllib.request
from dataclasses import dataclass

API = "https://pokeapi.co/api/v2"
HEADERS = {"User-Agent": "whos-that-pokemon (github.com/Alucad0/sidequest-sandbox)"}


def get_json(url: str) -> dict:
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


def get_bytes(url: str) -> bytes:
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.read()


def normalize(name: str) -> str:
    # "Mr. Mime", "mr-mime" and "mr mime" all become "mrmime"; "Flabébé" becomes "flabebe"
    decomposed = unicodedata.normalize("NFKD", name.lower())
    return "".join(c for c in decomposed if c.isalnum() and not unicodedata.combining(c))


def all_species() -> list[str]:
    # one request for every species name, used to pick a random index and to validate guesses
    data = get_json(f"{API}/pokemon-species?limit=100000")
    return [species["name"] for species in data["results"]]


def pretty(slug: str) -> str:
    return slug.replace("-", " ").title()


@dataclass
class Pokemon:
    name: str
    index: int
    generation: int
    types: list[str]
    abilities: list[str]
    sprite_url: str | None

    @classmethod
    def fetch(cls, index: int) -> Pokemon:
        species = get_json(f"{API}/pokemon-species/{index}/")
        default = next(v for v in species["varieties"] if v["is_default"])
        mon = get_json(default["pokemon"]["url"])

        # use the English display name ("Mr. Mime") rather than the API slug ("mr-mime")
        english = [n["name"] for n in species["names"] if n["language"]["name"] == "en"]
        name = english[0] if english else pretty(species["name"])

        # the generation url ends in its number, e.g. .../generation/3/
        generation = int(species["generation"]["url"].rstrip("/").split("/")[-1])

        return cls(
            name=name,
            index=index,
            generation=generation,
            types=[pretty(t["type"]["name"]) for t in mon["types"]],
            abilities=[pretty(a["ability"]["name"]) for a in mon["abilities"]],
            sprite_url=mon["sprites"]["front_default"],
        )

    def matches(self, guess: str) -> bool:
        return normalize(guess) == normalize(self.name)

    def letter_count(self) -> int:
        return len(normalize(self.name))

    def name_hint(self, show_first: bool) -> str:
        # one underscore per letter, keeping spaces and punctuation so "Mr. Mime" reads "_ _ .   _ _ _ _"
        hint = []
        for i, char in enumerate(self.name):
            if not char.isalnum():
                hint.append(char)
            elif i == 0 and show_first:
                hint.append(char.upper())
            else:
                hint.append("_")
        return " ".join(hint)
