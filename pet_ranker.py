#!/usr/bin/env python3
"""Rank fixed-rate OSRS boss pets by expected remaining completion time."""

__version__ = "0.6.0"

import argparse
import json
import math
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone


HISCORES_URL = "https://secure.runescape.com/m=hiscore_oldschool/index_lite.json"

# WikiSync (sync.runescape.wiki) used to be queried here for collection-log
# ownership, but the wiki's own server rejects third-party use of that
# endpoint (a browser-Origin request gets HTTP 403 "Please do not use
# WikiSync in your own projects", confirmed live 2026-09-05). Ownership
# detection is removed rather than worked around; --json snapshots now
# always report ownership_known: false and an empty owned_item_ids list.

# Times are deliberately editable estimates, not values supplied by the plugin.
# (pet, source, hiscore activity name, rarity denominator, minutes per attempt,
#  item id, assumed/simplified rate, attempt unit, rolls per attempt)
#
# attempt_unit / rolls_per_attempt (2026-09-05 schema generalization): most
# rows are a plain "kill" with 1 roll. A handful of instance/raid pets give
# several independent reward rolls per game/raid; for those, `rarity` is the
# wiki-verified chance PER ROLL and rolls_per_attempt factors out how many
# rolls one game/raid is worth, so expected_hours = rarity * minutes / 60 /
# rolls_per_attempt stays numerically identical to the old pre-refactor
# values (verified: 500*10/60 == 4000*10/60/8, 2500*5/60 == 5000*5/60/2,
# 1600*10/60 == 8000*10/60/5). See build_pet_data.py's METHOD_NOTES for
# the wiki citations behind each roll-based row's rarity/rolls figures.
PETS = (
    ("Abyssal orphan", "Abyssal Sire", "Abyssal Sire", 2560, 2.5, 13262, False, "kill", 1),
    ("Abyssal protector", "Guardians of the Rift", "Rifts closed", 4000, 10.0, 26901, True, "game", 8),
    ("Baron", "Duke Sucellus", "Duke Sucellus", 2500, 2.5, 28250, False, "kill", 1),
    ("Beef", "Brutus", "Brutus", 1000, 2.0, 33124, False, "kill", 1),
    ("Bran", "The Royal Titans", "The Royal Titans", 3000, 3.0, 30622, False, "kill", 1),
    ("Butch", "Vardorvis", "Vardorvis", 3000, 2.0, 28248, False, "kill", 1),
    ("Callisto cub", "Callisto", "Callisto", 1500, 3.0, 13178, True, "kill", 1),
    ("Callisto cub", "Artio", "Artio", 2800, 1.5, 13178, False, "kill", 1),
    ("Dom", "Doom of Mokhaiotl (delve 6)", "Doom of Mokhaiotl", 1000, 12.0, 31130, True, "kill", 1),
    ("Hellpuppy", "Cerberus", "Cerberus", 3000, 1.5, 13247, False, "kill", 1),
    ("Huberte", "The Hueycoatl (MVP)", "The Hueycoatl", 400, 4.0, 30152, True, "kill", 1),
    ("Ikkle hydra", "Alchemical Hydra", "Alchemical Hydra", 3000, 2.0, 22746, False, "kill", 1),
    ("Jal-nib-rek", "The Inferno", "TzKal-Zuk", 100, 90.0, 21291, True, "kill", 1),
    ("Kalphite princess", "Kalphite Queen", "Kalphite Queen", 3000, 2.5, 12647, False, "kill", 1),
    ("Lil' zik", "Theatre of Blood", "Theatre of Blood", 650, 20.0, 22473, True, "raid", 1),
    ("Lil'viathan", "The Leviathan", "The Leviathan", 2500, 2.0, 28252, False, "kill", 1),
    ("Little nightmare", "The Nightmare (solo)", "The Nightmare", 800, 18.0, 24491, True, "kill", 1),
    ("Little nightmare", "Phosani's Nightmare", "Phosani's Nightmare", 1400, 8.0, 24491, False, "kill", 1),
    ("Moxi", "Amoxliatl", "Amoxliatl", 3000, 1.5, 30154, False, "kill", 1),
    ("Muphin", "Phantom Muspah", "Phantom Muspah", 2500, 3.0, 27590, False, "kill", 1),
    ("Nexling", "Nex", "Nex", 500, 4.0, 26348, True, "kill", 1),
    ("Nid", "Araxxor", "Araxxor", 3000, 2.0, 29836, False, "kill", 1),
    ("Noon", "Grotesque Guardians", "Grotesque Guardians", 3000, 3.0, 21748, False, "kill", 1),
    ("Olmlet", "Chambers of Xeric (30k pts)", "Chambers of Xeric", 53, 25.0, 20851, True, "raid", 1),
    ("Pet chaos elemental", "Chaos Elemental", "Chaos Elemental", 300, 2.5, 11995, False, "kill", 1),
    ("Pet chaos elemental", "Chaos Fanatic", "Chaos Fanatic", 1000, 1.0, 11995, False, "kill", 1),
    ("Pet dagannoth prime", "Dagannoth Kings", "Dagannoth Prime", 5000, 1.0, 12644, False, "kill", 1),
    ("Pet dagannoth rex", "Dagannoth Kings", "Dagannoth Rex", 5000, 1.0, 12645, False, "kill", 1),
    ("Pet dagannoth supreme", "Dagannoth Kings", "Dagannoth Supreme", 5000, 1.0, 12643, False, "kill", 1),
    ("Pet dark core", "Corporeal Beast", "Corporeal Beast", 5000, 4.0, 12816, False, "kill", 1),
    ("Pet general graardor", "General Graardor (Bandos GWD)", "General Graardor", 5000, 1.5, 12650, False, "kill", 1),
    ("Pet k'ril tsutsaroth", "K'ril Tsutsaroth (Zamorak GWD)", "K'ril Tsutsaroth", 5000, 1.5, 12652, False, "kill", 1),
    ("Pet kraken", "Kraken", "Kraken", 3000, 1.0, 12655, False, "kill", 1),
    ("Pet kree'arra", "Kree'arra (Armadyl GWD)", "Kree'Arra", 5000, 2.0, 12649, False, "kill", 1),
    ("Pet smoke devil", "Thermonuclear Smoke Devil", "Thermonuclear Smoke Devil", 3000, 1.0, 12648, False, "kill", 1),
    ("Pet snakeling", "Zulrah", "Zulrah", 4000, 1.5, 12921, False, "kill", 1),
    ("Pet zilyana", "Commander Zilyana (Saradomin GWD)", "Commander Zilyana", 5000, 1.5, 12651, False, "kill", 1),
    ("Phoenix", "Wintertodt (~2 crates/game)", "Wintertodt", 5000, 5.0, 20693, True, "game", 2),
    ("Prince black dragon", "King Black Dragon", "King Black Dragon", 3000, 1.5, 12653, False, "kill", 1),
    ("Scorpia's offspring", "Scorpia", "Scorpia", 2016, 1.0, 13181, False, "kill", 1),
    ("Scurry", "Scurrius", "Scurrius", 3000, 1.0, 28801, False, "kill", 1),
    ("Skotos", "Skotizo", "Skotizo", 65, 4.0, 21273, False, "kill", 1),
    ("Smol heredit", "Sol Heredit", "Sol Heredit", 200, 35.0, 28960, False, "kill", 1),
    ("Smolcano", "Zalcano", "Zalcano", 2250, 3.0, 23760, False, "kill", 1),
    ("Sraracha", "Sarachnis", "Sarachnis", 3000, 1.5, 23495, False, "kill", 1),
    ("Tiny tempor", "Tempoross (~5 permits/game)", "Tempoross", 8000, 10.0, 25602, True, "game", 5),
    ("Tumeken's guardian", "Tombs of Amascut (300, ~30k pts)", "Tombs of Amascut: Expert Mode", 467, 25.0, 27352, True, "raid", 1),
    ("Tzrek-jad", "TzHaar Fight Cave", "TzTok-Jad", 200, 40.0, 13225, True, "kill", 1),
    ("Venenatis spiderling", "Venenatis", "Venenatis", 1500, 3.0, 13177, True, "kill", 1),
    ("Venenatis spiderling", "Spindel", "Spindel", 2800, 1.5, 13177, False, "kill", 1),
    ("Vet'ion jr.", "Vet'ion", "Vet'ion", 1500, 3.0, 13179, True, "kill", 1),
    ("Vet'ion jr.", "Calvar'ion", "Calvar'ion", 2800, 1.5, 13179, False, "kill", 1),
    ("Vorki", "Vorkath", "Vorkath", 3000, 1.5, 21992, False, "kill", 1),
    ("Wisp", "The Whisperer", "The Whisperer", 2000, 2.5, 28246, False, "kill", 1),
    ("Yami", "Yama", "Yama", 2500, 3.0, 30888, False, "kill", 1),
    ("Youngllef", "The Gauntlet", "The Gauntlet", 2000, 6.0, 23757, False, "kill", 1),
    ("Youngllef", "The Corrupted Gauntlet", "The Corrupted Gauntlet", 800, 10.0, 23757, False, "kill", 1),
)

DEFAULT_SNAPSHOT_PATH = "pet_ranker_snapshot.json"


def fetch_activities(username):
    url = HISCORES_URL + "?" + urllib.parse.urlencode({"player": username})
    request = urllib.request.Request(url, headers={"User-Agent": "pet-ranker/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise ValueError(f"Player not found: {username}") from exc
        raise ValueError(f"Hiscores request failed (HTTP {exc.code})") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ValueError(f"Could not reach OSRS hiscores: {exc.reason}") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("OSRS hiscores returned invalid JSON") from exc

    if not isinstance(payload, dict) or not isinstance(payload.get("activities"), list):
        raise ValueError("Unexpected hiscores JSON layout: missing activities list")

    activities = {}
    for entry in payload["activities"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
            continue
        value = entry.get("score", entry.get("level", -1))
        if isinstance(value, int):
            activities[entry["name"].casefold()] = max(0, value)
    return activities


def print_ranking(activities):
    rows = []
    missing = []
    for pet, source, activity, rate, minutes, item_id, assumed, attempt_unit, rolls in PETS:
        key = activity.casefold()
        if key not in activities:
            missing.append(activity)
            kc = 0
        else:
            kc = activities[key]
        expected_hours = rate * minutes / 60.0 / rolls
        chance = -math.expm1((kc * rolls) * math.log1p(-1.0 / rate))
        rows.append((expected_hours, pet, source, rate, kc, minutes, chance, assumed))

    rows.sort(key=lambda row: (row[0], row[1]))
    header = f"{'#':>2}  {'Pet':<24} {'Source':<38} {'Rate':>8} {'KC':>8} {'Min/kill':>8} {'Remain h':>10} {'KC chance':>10}"
    print(header)
    print("-" * len(header))
    for rank, (hours, pet, source, rate, kc, minutes, chance, assumed) in enumerate(rows, 1):
        rate_text = ("~" if assumed else "") + "1/" + str(rate)
        print(f"{rank:>2}  {pet:<24.24} {source:<38.38} {rate_text:>8} {kc:>8,} {minutes:>8.1f} {hours:>10,.1f} {chance:>9.2%}")

    if missing:
        unique = ", ".join(dict.fromkeys(missing))
        print(f"\nNote: activity absent from this hiscore response; KC shown as 0: {unique}", file=sys.stderr)
    print("\nKC chance is 1-(1-1/N)^KC; it is context, not proof the pet is owned.")
    print("Expected remaining time is N * minutes/kill / 60 and is independent of KC.")
    print("~ = assumed/simplified rate (raid points, team size, or mode variants approximated)")


def build_snapshot(username, activities):
    """Build a JSON-serializable snapshot of ranking inputs/outputs for the web pet wheel.

    There is no ownership source any more (WikiSync is off-limits, see the
    comment above HISCORES_URL), so ownership_known is always False and
    owned_item_ids is always empty. Callers (pet-wheel.html) treat that
    as "ownership unknown, show every pet" rather than "nothing owned".

    Skilling pets are out of scope for this module entirely (rarity/rate are
    user-editable in the wheel page, not a hiscore-driven estimate); they and
    the fixed-rate minigame/clue pets live only in pets.json +
    build_pet_data.py. PETS here covers per-kill bosses plus the
    roll-based instance/raid pets that DO have a hiscore-trackable KC
    (Tempoross/Wintertodt/GotR/CoX/ToA/ToB/Hueycoatl/Zalcano), each carrying
    its own attempt_unit and rolls_per_attempt. assumed_rate is the old
    "assumed" flag renamed to match the wheel's unified field names.
    """
    kc_by_activity = {}
    pets_out = []
    for pet, source, activity, rate, minutes, item_id, assumed, attempt_unit, rolls in PETS:
        kc = activities.get(activity.casefold(), 0)
        kc_by_activity[activity] = kc
        expected_hours = rate * minutes / 60.0 / rolls
        pets_out.append(
            {
                "name": pet,
                "source": source,
                "activity": activity,
                "rarity": rate,
                "minutes_per_attempt": minutes,
                "item_id": item_id,
                "assumed_rate": assumed,
                "attempt_unit": attempt_unit,
                "rolls_per_attempt": rolls,
                "kc": kc,
                "expected_hours": expected_hours,
                "owned": False,
            }
        )

    return {
        "rsn": username,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "owned_item_ids": [],
        "ownership_known": False,
        "kc": kc_by_activity,
        "pets": pets_out,
    }


def build_arg_parser():
    parser = argparse.ArgumentParser(
        prog="pet_ranker.py",
        description="Rank fixed-rate OSRS boss pets by expected remaining completion time.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            '  python pet_ranker.py --rsn "a tbow"\n'
            '  python pet_ranker.py --rsn "a tbow" --json snapshot.example.json\n'
        ),
    )
    parser.add_argument(
        "--rsn",
        metavar="NAME",
        help="OSRS username to look up; skips the interactive prompt when given",
    )
    parser.add_argument(
        "--json",
        metavar="PATH",
        nargs="?",
        const=DEFAULT_SNAPSHOT_PATH,
        default=None,
        help=(
            "Write a JSON snapshot (for pet-wheel.html) to PATH instead of printing "
            f"the table (default path if PATH omitted: {DEFAULT_SNAPSHOT_PATH})"
        ),
    )
    return parser


def main():
    parser = build_arg_parser()
    args = parser.parse_args()

    if args.rsn:
        username = args.rsn.strip()
    else:
        print(f"pet_ranker v{__version__}")
        username = input("OSRS username: ").strip()

    if not username:
        print("Username cannot be empty.", file=sys.stderr)
        return 2

    try:
        activities = fetch_activities(username)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        snapshot = build_snapshot(username, activities)
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(snapshot, fh, indent=2)
        print(args.json)
    else:
        print_ranking(activities)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
