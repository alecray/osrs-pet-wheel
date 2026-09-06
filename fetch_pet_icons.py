"""Download each pet's inventory icon from the OSRS Wiki into data/icons/.

Icons are the wiki's item images (CC BY-NC-SA 3.0, see README credits).
build_pet_data.py embeds whatever is present in data/icons/ as base64 so
pet-wheel.html keeps working offline. Re-run this after adding a pet to
data/pets.json. Existing files are skipped unless --force is given.

Usage:
    python fetch_pet_icons.py [--force]
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
ICON_DIR = ROOT / "data" / "icons"
WIKI_API = "https://oldschool.runescape.wiki/api.php"
USER_AGENT = "osrs-pet-wheel fetch_pet_icons.py (https://github.com/alecray/osrs-pet-wheel)"


def get(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def icon_filename(slug: str) -> str:
    """Return the file name from the pet page's Infobox Item image field."""
    title = urllib.parse.unquote(slug).replace("_", " ")
    params = {"action": "query", "prop": "revisions", "rvprop": "content", "rvslots": "main",
              "titles": title, "redirects": "1", "format": "json"}
    data = json.loads(get(WIKI_API + "?" + urllib.parse.urlencode(params)))
    page = next(iter(data["query"]["pages"].values()))
    text = page["revisions"][0]["slots"]["main"]["*"]
    item = text.find("{{Infobox Item")
    scope = text[item:] if item >= 0 else text
    m = re.search(r"\|\s*image\d*\s*=\s*\[\[File:([^\]|]+)", scope)
    if not m:
        raise ValueError("no image in infobox")
    return m.group(1).strip()


def icon_slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def main() -> int:
    force = "--force" in sys.argv
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    pets = json.loads(PETS_JSON.read_text(encoding="utf-8"))
    failed = []
    for pet in pets:
        out = ICON_DIR / (icon_slug(pet["name"]) + ".png")
        if out.exists() and not force:
            continue
        try:
            fname = icon_filename(pet["wikiUrl"].rsplit("/w/", 1)[1])
            url = "https://oldschool.runescape.wiki/images/" + urllib.parse.quote(fname.replace(" ", "_"))
            out.write_bytes(get(url))
            print(f"ok   {pet['name']}: {fname}")
        except Exception as exc:  # noqa: BLE001 - report and continue
            failed.append(pet["name"])
            print(f"FAIL {pet['name']}: {exc}")
        time.sleep(0.25)
    if failed:
        print(f"\n{len(failed)} icon(s) missing: {', '.join(failed)}")
        return 1
    print("\nAll icons present.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
