#!/usr/bin/env python3
"""Regenerate the embedded <script id="pet-data"> block in pet-wheel.html.

Merges two pet datasets that already exist in this repo:

  - data/pets.json
    (wikiUrl, type, itemId, defaultTags, plus -- as of the 2026-09-05
    "attempts not kills" schema generalization -- rarity/attemptUnit/
    rollsPerAttempt/attemptsPerHour/methodNote/assumedRate/editable/womSkill
    for pets that have no pet_ranker.py timing row; this is the same dataset
    the RuneLite plugin at github.com/alecray/runelite-pet-hunter ships)
  - pet_ranker.py's PETS tuple
    (rarity, minutes-per-attempt, hiscore activity name, attempt_unit,
    rolls_per_attempt, assumed_rate -- kept there ONLY for fixed-rate boss
    kills and the hiscore-trackable roll/raid pets; see that module's
    docstring)

A pet is included in the wheel dataset if EITHER source can supply a timing
estimate: a pet_ranker.py PETS row, or pets.json's own attemptUnit/
attemptsPerHour fields. Two pets are permanently excluded regardless (see
EXCLUDED_PETS): Broav and Cat are quest rewards, not repeatable grinds, so
they have no attempt-based rate and don't belong on a hunt wheel.

When a pet has multiple PETS rows (different kill methods, e.g. Callisto
cub via Callisto or via Artio), the fastest method (lowest expected hours)
is used for the wheel's default weighting -- this mirrors pet_ranker.py's
own "quickest first" ranking philosophy.

Run this after editing pets.json or pet_ranker.py's PETS tuple:
    python build_pet_data.py
"""
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PETS_JSON_PATH = ROOT / "data/pets.json"
PET_RANKER_PATH = ROOT / "pet_ranker.py"
HTML_PATH = ROOT / "pet-wheel.html"

PET_DATA_BLOCK_RE = re.compile(
    r'(<script id="pet-data" type="application/json">\n).*?(\n</script>)',
    re.DOTALL,
)

# Pets excluded from the wheel permanently, regardless of any rate data:
# both are one-time quest rewards (While Guthix Sleeps / Gertrude's Cat),
# not repeatable content, so "expected hours to obtain" is meaningless for
# them. pets.json keeps their entries (the RuneLite plugin still tracks them
# in the collection log); only the wheel excludes them.
EXCLUDED_PETS = {"Broav", "Cat"}

# Filter-tab category (All / Bosses / Skilling / Minigame). Owner spec
# (2026-09-05): Skilling = the 9 pure skill-training pets plus Herbi and
# Quetzin; Minigame = the roll-based minigame/clue pets named below.
# pets.json's own defaultTags predate this three-way split and don't
# disambiguate it cleanly (e.g. Zalcano/Tempoross/Wintertodt/GotR carry a
# "skilling" or "boss" tag from before this feature existed, and Fight
# Caves/Inferno/Gauntlet/the raids carry a legacy "minigame" tag despite
# being boss-style combat encounters), so this table is the authoritative
# mapping rather than a live tag read. Everything not listed is "boss".
SKILLING_PETS = {
    "Baby chinchompa", "Beaver", "Giant squirrel", "Heron", "Rift guardian",
    "Rock golem", "Rocky", "Soup", "Tangleroot", "Herbi", "Quetzin",
}
MINIGAME_PETS = {
    "Abyssal protector", "Bloodhound", "Chompy chick", "Lil' creator",
    "Pet penance queen", "Phoenix", "Smolcano", "Tiny tempor",
}


def derive_category(name):
    if name in SKILLING_PETS:
        return "skilling"
    if name in MINIGAME_PETS:
        return "minigame"
    return "boss"


# methodNote text for the roll/raid pets whose rate lives in pet_ranker.py's
# PETS tuple (so the tuple itself doesn't need a 10th free-text column).
# Each cites the OSRS Wiki page(s) the rarity/rolls-per-attempt figures were
# checked against (2026-09-05).
METHOD_NOTES = {
    "Abyssal protector": (
        "Guardians of the Rift, per Rewards Guardian roll (wiki confirms "
        "1/4,000). Rolls/game (8) is an inherited community estimate, not "
        "wiki-stated -- edit if you track your own rate. "
        "https://oldschool.runescape.wiki/w/Abyssal_protector"
    ),
    "Phoenix": (
        "Wintertodt supply crates (wiki: exchanging a full Pyromancer "
        "outfit for a crate gives 4 loot rolls, used here as a proxy for "
        "~2 crates from a typical game). True per-crate rate and crates/game "
        "aren't both wiki-confirmed together -- treat as approximate. "
        "https://oldschool.runescape.wiki/w/Phoenix_(pet)"
    ),
    "Tiny tempor": (
        "Tempoross reward permits (wiki: 1 permit per 2,000 points, +1 per "
        "700 points beyond that). ~5 permits/game is an inherited community "
        "estimate for normal (non-Leagues) play, not wiki-stated for a "
        "typical game -- edit if you track your own rate. "
        "https://oldschool.runescape.wiki/w/Tiny_tempor"
    ),
    "Olmlet": (
        "Chambers of Xeric, 1/53 per unique drop from the loot table (wiki-"
        "confirmed exact figure). Treated as ~1 unique-roll-equivalent per "
        "raid at ~30,000 points; the wiki doesn't state uniques-per-raid "
        "directly, so expected hours here are approximate. Challenge Mode's "
        "improved rate was not added as a separate row -- the wiki excerpts "
        "checked didn't give a clean, distinct CM denominator. "
        "https://oldschool.runescape.wiki/w/Olmlet"
    ),
    "Tumeken's guardian": (
        "Tombs of Amascut reward chest (wiki confirms a chance exists, "
        "scaled by raid level/points, but not an exact 1/N or points-per-"
        "raid figure). Rarity/minutes here are an inherited community "
        "estimate for a ~30,000-point (300 raid level) run. Expert Mode's "
        "improved rate was not added as a separate row for the same reason "
        "as CM above. https://oldschool.runescape.wiki/w/Tumeken's_guardian"
    ),
    "Lil' zik": (
        "Theatre of Blood monumental chest (wiki confirms the range "
        "1/650-1/6,500, best case at 10 individual points, which is the "
        "figure used here). Hard Mode's improved range (1/500-1/5,000) was "
        "not added as a separate row -- treat this as the normal-mode best "
        "case. https://oldschool.runescape.wiki/w/Lil'_zik"
    ),
    "Huberte": (
        "The Hueycoatl, 1/400 base rate scaled by personal damage "
        "contribution (wiki-confirmed exact figure; MVP/top-damage is NOT "
        "required, just a minimum damage threshold). "
        "https://oldschool.runescape.wiki/w/Huberte"
    ),
    "Smolcano": (
        "Zalcano, static 1/2,250 per kill for any eligible player (wiki-"
        "confirmed exact figure, replacing the old 1/1,500-1/2,775 "
        "performance-scaled rate). Single roll per kill, not a multi-roll "
        "minigame mechanic. https://oldschool.runescape.wiki/w/Smolcano"
    ),
}

# pet_ranker.py's "activity" (OSRS hiscores name) -> Wise Old Man's snake_case
# boss metric, verified live against https://api.wiseoldman.net/v2/efficiency
# /rates?metric=ehb&type=main (2026-09-05). Anything not in that response
# (Guardians of the Rift, Wintertodt, Zalcano, Tempoross -- all ehb:0
# skilling/minigame content) maps to None: the wheel falls back to the
# hardcoded minutes_per_attempt estimate for those.
WOM_METRIC_BY_ACTIVITY = {
    "Abyssal Sire": "abyssal_sire",
    "Rifts closed": None,
    "Duke Sucellus": "duke_sucellus",
    "Brutus": "brutus",
    "The Royal Titans": "the_royal_titans",
    "Vardorvis": "vardorvis",
    "Callisto": "callisto",
    "Artio": "artio",
    "Doom of Mokhaiotl": "doom_of_mokhaiotl",
    "Cerberus": "cerberus",
    "The Hueycoatl": "the_hueycoatl",
    "Alchemical Hydra": "alchemical_hydra",
    "TzKal-Zuk": "tzkal_zuk",
    "Kalphite Queen": "kalphite_queen",
    "Theatre of Blood": "theatre_of_blood",
    "The Leviathan": "the_leviathan",
    "The Nightmare": "nightmare",
    "Phosani's Nightmare": "phosanis_nightmare",
    "Amoxliatl": "amoxliatl",
    "Phantom Muspah": "phantom_muspah",
    "Nex": "nex",
    "Araxxor": "araxxor",
    "Grotesque Guardians": "grotesque_guardians",
    "Chambers of Xeric": "chambers_of_xeric",
    "Chaos Elemental": "chaos_elemental",
    "Chaos Fanatic": "chaos_fanatic",
    "Dagannoth Prime": "dagannoth_prime",
    "Dagannoth Rex": "dagannoth_rex",
    "Dagannoth Supreme": "dagannoth_supreme",
    "Corporeal Beast": "corporeal_beast",
    "General Graardor": "general_graardor",
    "K'ril Tsutsaroth": "kril_tsutsaroth",
    "Kraken": "kraken",
    "Kree'Arra": "kreearra",
    "Thermonuclear Smoke Devil": "thermonuclear_smoke_devil",
    "Zulrah": "zulrah",
    "Commander Zilyana": "commander_zilyana",
    "Wintertodt": None,
    "King Black Dragon": "king_black_dragon",
    "Scorpia": "scorpia",
    "Scurrius": "scurrius",
    "Skotizo": "skotizo",
    "Sol Heredit": "sol_heredit",
    "Zalcano": None,
    "Sarachnis": "sarachnis",
    "Tempoross": None,
    "Tombs of Amascut: Expert Mode": "tombs_of_amascut_expert",
    "TzTok-Jad": "tztok_jad",
    "Venenatis": "venenatis",
    "Spindel": "spindel",
    "Vet'ion": "vetion",
    "Calvar'ion": "calvarion",
    "Vorkath": "vorkath",
    "The Whisperer": "the_whisperer",
    "Yama": "yama",
    "The Gauntlet": "the_gauntlet",
    "The Corrupted Gauntlet": "the_corrupted_gauntlet",
}

# Wise Old Man metric for pets.json-native pets (no pet_ranker.py PETS row,
# so no hiscore "activity" name to look up above). Verified live against
# a WOM player snapshot (2026-09-05): clue_scrolls_master exists as an
# "activity" metric (score field, not kills). soul_wars_zeal also exists but
# is a points total, not a game count, so it isn't wired up as a KC-style
# attempt counter -- Lil' creator maps to None (see README "Known gaps").
# No barbarian_assault metric exists on WOM at all.
WOM_METRIC_BY_PET = {
    "Bloodhound": "clue_scrolls_master",
}

# WOM splits player snapshots into a `bosses` namespace (kills) and an
# `activities` namespace (score) -- clue_scrolls_master lives under
# activities, so pet-wheel.html needs to know which table to look in.
# Rows with no WOM_METRIC_BY_PET entry never consult this.
WOM_TYPE_BY_PET = {
    "Bloodhound": "activity",
}


def load_pet_ranker():
    """Import pet_ranker.py by path so this script works regardless of cwd.

    pet_ranker.py only fetches network data / prompts inside main(), which
    runs under `if __name__ == "__main__"` -- importing it is side-effect
    free and just gives us the PETS tuple.
    """
    spec = importlib.util.spec_from_file_location("pet_ranker", PET_RANKER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_dataset():
    pet_ranker = load_pet_ranker()
    pets_json = json.loads(PETS_JSON_PATH.read_text(encoding="utf-8"))
    meta_by_name = {p["name"]: p for p in pets_json}

    best_by_name = {}
    for pet, source, activity, rarity, minutes, item_id, assumed, attempt_unit, rolls in pet_ranker.PETS:
        expected_hours = rarity * minutes / 60.0 / rolls
        current = best_by_name.get(pet)
        if current is None or expected_hours < current["expected_hours"]:
            best_by_name[pet] = {
                "name": pet,
                "source": source,
                "activity": activity,
                "rarity": rarity,
                "minutes_per_attempt": minutes,
                "item_id": item_id,
                "assumedRate": assumed,
                "attemptUnit": attempt_unit,
                "rollsPerAttempt": rolls,
                "expected_hours": expected_hours,
            }

    dataset = []
    skipped_no_json_match = []
    excluded = []
    for name, meta in meta_by_name.items():
        if name in EXCLUDED_PETS:
            excluded.append(name)
            continue

        row = best_by_name.get(name)
        if row is not None:
            # pets.json is missing itemId for several newer pets (recorded as
            # 0); pet_ranker.py's PETS tuple has real ids for most of those,
            # so prefer pets.json's id only when it is actually populated.
            item_id = meta.get("itemId") or row["item_id"]
            dataset.append({
                "name": row["name"],
                "source": row["source"],
                "activity": row["activity"],
                "category": derive_category(row["name"]),
                "rarity": row["rarity"],
                "minutes_per_attempt": row["minutes_per_attempt"],
                "attemptUnit": row["attemptUnit"],
                "rollsPerAttempt": row["rollsPerAttempt"],
                "assumedRate": row["assumedRate"],
                "methodNote": METHOD_NOTES.get(row["name"]),
                "editable": False,
                "womSkill": None,
                "item_id": item_id,
                "wikiUrl": meta.get("wikiUrl", ""),
                "type": meta.get("type", "SOLO"),
                "wom": WOM_METRIC_BY_ACTIVITY.get(row["activity"]),
                "womType": "boss",
            })
            continue

        # No pet_ranker.py row -- fall back to pets.json's own attempt-rate
        # fields (skilling pets + the 4 fixed-rate minigame/clue pets added
        # in the 2026-09-05 schema generalization). Skip silently only if
        # neither source has a timing estimate at all.
        attempts_per_hour = meta.get("attemptsPerHour")
        if not meta.get("attemptUnit") or not attempts_per_hour or not meta.get("rarity"):
            skipped_no_json_match.append(name)
            continue

        rolls = meta.get("rollsPerAttempt", 1)
        minutes_per_attempt = 60.0 / attempts_per_hour
        dataset.append({
            "name": name,
            "source": meta.get("source", ""),
            "activity": None,
            "category": derive_category(name),
            "rarity": meta["rarity"],
            "minutes_per_attempt": minutes_per_attempt,
            "attemptUnit": meta["attemptUnit"],
            "rollsPerAttempt": rolls,
            "assumedRate": bool(meta.get("assumedRate", True)),
            "methodNote": meta.get("methodNote"),
            "editable": bool(meta.get("editable", False)),
            "womSkill": meta.get("womSkill"),
            "item_id": meta.get("itemId", 0),
            "wikiUrl": meta.get("wikiUrl", ""),
            "type": meta.get("type", "SOLO"),
            "wom": WOM_METRIC_BY_PET.get(name),
            "womType": WOM_TYPE_BY_PET.get(name, "boss"),
        })

    dataset.sort(key=lambda r: r["name"])

    if excluded:
        print(
            f"Note: {len(excluded)} pet(s) permanently excluded from the wheel (quest rewards): "
            + ", ".join(sorted(excluded)),
            file=sys.stderr,
        )
    if skipped_no_json_match:
        print(
            f"Note: {len(skipped_no_json_match)} pets.json pet(s) skipped (no timing estimate in "
            "either pet_ranker.py or pets.json's own attempt-rate fields): "
            + ", ".join(sorted(skipped_no_json_match)),
            file=sys.stderr,
        )

    return dataset


def inject(dataset):
    html = HTML_PATH.read_text(encoding="utf-8")
    payload = json.dumps(dataset, indent=2)
    if not PET_DATA_BLOCK_RE.search(html):
        raise SystemExit('Could not find <script id="pet-data"> block in pet-wheel.html')
    html = PET_DATA_BLOCK_RE.sub(lambda m: m.group(1) + payload + m.group(2), html, count=1)
    HTML_PATH.write_text(html, encoding="utf-8")


def main():
    dataset = build_dataset()
    inject(dataset)
    print(f"Wrote {len(dataset)} pets into {HTML_PATH}")


if __name__ == "__main__":
    main()
