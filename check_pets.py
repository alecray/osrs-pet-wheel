"""Compare data/pets.json against the OSRS Wiki and report drift.

Two checks, both read-only:

  1. New pets: every page in the wiki's Category:Pets that has no row in
     pets.json. Cosmetic/quest followers (cats, gnome child, ...) are
     listed in IGNORED_PAGES so they do not nag forever; add a page there
     when it is deliberately excluded, or add a real row when it is a
     huntable pet.
  2. Item IDs: every populated `itemId` in pets.json must appear in that
     pet's wiki infobox. A wrong ID silently breaks ownership detection
     (the pet never leaves the hunt list), which is how Scurry went
     unnoticed.

Exit status is 1 when either check finds something, so CI can fail on it.

Usage:
    python check_pets.py
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PETS_JSON = ROOT / "data" / "pets.json"
WIKI_API = "https://oldschool.runescape.wiki/api.php"
USER_AGENT = "osrs-pet-wheel check_pets.py (https://github.com/alecray/osrs-pet-wheel)"

# Category:Pets members that are not huntable drops: quest/cosmetic
# followers, variants of an existing pet, and wiki meta pages.
IGNORED_PAGES = {
    "Pet",
    "Non-pet followers",
    "Metamorphosis",
    "Karamthulhu (unused pet)",
    # cats
    "Kitten", "Hellcat", "Lazy cat", "Overgrown cat", "Wily cat", "Toy cat",
    "Fishbowl (pet)",
    # quest / one-off followers
    "Baby Mole", "Pet rock", "Humphrey Dumphrey", "Mayor of Catherby", "Mr McGroot",
    "Dr banikan (item)", "Elias white (item)", "Gary (item)", "Gnome child (item)",
    "Grubfoot (item)", "Ivan strom (item)", "Knight of Varlamore (item)", "Nieve (item)",
    "Prince itzla arkan (item)", "Silif (item)", "Veliaf hurtz (item)",
    # Beaver metamorphs unlocked by Forestry items, not separate drops
    "Fox (pet)", "Pheasant (pet)",
}


def api(params: dict) -> dict:
    params = dict(params, format="json")
    url = WIKI_API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def wiki_pet_pages() -> list[str]:
    titles: list[str] = []
    params = {"action": "query", "list": "categorymembers", "cmtitle": "Category:Pets", "cmlimit": "500", "cmnamespace": "0"}
    while True:
        data = api(params)
        titles.extend(m["title"] for m in data["query"]["categorymembers"])
        cont = data.get("continue")
        if not cont:
            return titles
        params.update(cont)


def page_wikitext(title: str) -> str | None:
    data = api({"action": "query", "prop": "revisions", "rvprop": "content", "rvslots": "main", "titles": title, "redirects": "1"})
    page = next(iter(data["query"]["pages"].values()))
    try:
        return page["revisions"][0]["slots"]["main"]["*"]
    except (KeyError, IndexError):
        return None


def infobox_item_ids(wikitext: str) -> set[int]:
    return {int(x) for x in re.findall(r"\|\s*id\d*\s*=\s*(\d+)", wikitext)}


def normalise(title: str) -> str:
    return re.sub(r"\s*\((pet|item)\)$", "", title).casefold()


def main() -> int:
    pets = json.loads(PETS_JSON.read_text(encoding="utf-8"))
    known = {normalise(p["name"]) for p in pets}
    problems = 0

    print("== New pets on the wiki not in data/pets.json ==")
    new = [t for t in wiki_pet_pages() if t not in IGNORED_PAGES and normalise(t) not in known]
    for t in new:
        print(f"  NEW  {t}  https://oldschool.runescape.wiki/w/{urllib.parse.quote(t.replace(' ', '_'))}")
    if not new:
        print("  none")
    problems += len(new)

    print("== Item ID check ==")
    for p in pets:
        if not p.get("itemId"):
            continue
        title = urllib.parse.unquote(p["wikiUrl"].rsplit("/w/", 1)[1]).replace("_", " ")
        text = page_wikitext(title)
        if text is None:
            print(f"  ERR  {p['name']}: could not read wiki page '{title}'")
            problems += 1
            continue
        ids = infobox_item_ids(text)
        if p["itemId"] not in ids:
            print(f"  BAD  {p['name']}: pets.json={p['itemId']} wiki={sorted(ids)}")
            problems += 1
        time.sleep(0.2)
    print("  done")

    if problems:
        print(f"\n{problems} problem(s) found.")
        return 1
    print("\nAll good.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
