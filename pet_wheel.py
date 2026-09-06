#!/usr/bin/env python3
"""One-command local launcher + sync server for pet-wheel.html.

Starts a local HTTP server on 127.0.0.1 that serves this repo's root
directory (so the wheel page loads at http://127.0.0.1:<port>/pet-wheel.html)
and exposes two JSON endpoints the page calls itself:

    GET /api/ping           -> {"ok": true}
    GET /api/sync?rsn=NAME  -> a pet_ranker.py --json -shaped snapshot, but
                               with real pet ownership (ownership_known:
                               true, owned_item_ids, owned_counts) pulled
                               from RuneProfile (https://runeprofile.com),
                               an unofficial public API with no CORS headers
                               -- hence this server sits in between so the
                               page (served over http or opened as file://)
                               can reach it from the browser.

RuneProfile is unofficial and could change or disappear without notice; if
`/api/sync` starts failing, pet-wheel.html still works fully offline with
whatever snapshot was last cached (see README).

Usage:
    python pet_wheel.py [--rsn NAME] [--port 8231] [--no-open]

"a tbow" is only the documented example account, not a hardcoded default
target for anyone else's use of this tool -- pass --rsn for any account.
"""

import argparse
import functools
import json
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

__version__ = "0.1.0"

# pet_wheel.py, pet-wheel.html, and pet_ranker.py all sit side by side at the
# repo root -- this directory is both what gets served and where pet_ranker
# is imported from (Python already puts a script's own directory on
# sys.path, so no path hack is needed).
APP_DIR = Path(__file__).resolve().parent
SNAPSHOT_CACHE_PATH = APP_DIR / "snapshot.latest.json"

import pet_ranker  # noqa: E402  (must follow sys.path being set up by the interpreter)

RUNEPROFILE_URL = "https://api.runeprofile.com/profiles/{}"
DEFAULT_RSN = "a tbow"
DEFAULT_PORT = 8231

_state_lock = threading.Lock()
_cached_snapshot = None


def fetch_runeprofile_items(rsn):
    """Return the RuneProfile `items` list (collection-log items) for rsn.

    Raises ValueError with a user-facing message on any failure; never lets
    a raw urllib/json exception escape.
    """
    url = RUNEPROFILE_URL.format(urllib.parse.quote(rsn, safe=""))
    request = urllib.request.Request(url, headers={"User-Agent": "pet-wheel-local-sync/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise ValueError(f"RuneProfile has no profile for: {rsn}") from exc
        raise ValueError(f"RuneProfile request failed (HTTP {exc.code})") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ValueError(f"Could not reach RuneProfile: {exc.reason}") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("RuneProfile returned invalid JSON") from exc

    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise ValueError("Unexpected RuneProfile JSON layout: missing items list")
    return payload["items"]


def build_sync_snapshot(rsn):
    """Build a pet_ranker.py --json -shaped snapshot with real ownership.

    Reuses pet_ranker.fetch_activities() (hiscores) and
    pet_ranker.build_snapshot() (shared shape), then layers RuneProfile
    ownership on top. Raises ValueError on any upstream failure.
    """
    activities = pet_ranker.fetch_activities(rsn)
    items = fetch_runeprofile_items(rsn)

    owned_item_ids = []
    owned_counts = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        item_id = item.get("id")
        quantity = item.get("quantity", 0)
        if not isinstance(item_id, int) or not isinstance(quantity, int):
            continue
        if quantity > 0:
            owned_item_ids.append(item_id)
            owned_counts[str(item_id)] = quantity

    snapshot = pet_ranker.build_snapshot(rsn, activities)
    snapshot["ownership_known"] = True
    snapshot["owned_item_ids"] = owned_item_ids
    snapshot["owned_counts"] = owned_counts
    snapshot["source"] = "runeprofile+hiscores"
    owned_set = set(owned_item_ids)
    for pet in snapshot["pets"]:
        pet["owned"] = pet["item_id"] in owned_set
    return snapshot


def run_sync(rsn):
    """Run one sync, cache it in memory and on disk, and return it."""
    global _cached_snapshot
    snapshot = build_sync_snapshot(rsn)
    with _state_lock:
        _cached_snapshot = snapshot
    try:
        SNAPSHOT_CACHE_PATH.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    except OSError as exc:
        print(f"Warning: could not write {SNAPSHOT_CACHE_PATH}: {exc}", file=sys.stderr)
    return snapshot


class SyncRequestHandler(SimpleHTTPRequestHandler):
    def _send_json(self, status, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/api/ping":
            self._send_json(200, {"ok": True})
            return

        if parsed.path == "/api/sync":
            query = urllib.parse.parse_qs(parsed.query)
            rsn = (query.get("rsn", [""])[0] or "").strip()
            if not rsn:
                self._send_json(502, {"error": "Missing rsn query parameter"})
                return
            try:
                snapshot = run_sync(rsn)
            except ValueError as exc:
                self._send_json(502, {"error": str(exc)})
                return
            except Exception as exc:  # pragma: no cover - safety net, never leak a traceback
                self._send_json(502, {"error": f"Unexpected error: {exc}"})
                return
            self._send_json(200, snapshot)
            return

        super().do_GET()

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))


def build_arg_parser():
    parser = argparse.ArgumentParser(
        prog="pet_wheel.py",
        description="One-command local launcher + sync server for pet-wheel.html.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            '  python pet_wheel.py --rsn "a tbow"\n'
            "  python pet_wheel.py --port 9000 --no-open\n"
        ),
    )
    parser.add_argument(
        "--rsn",
        metavar="NAME",
        default=DEFAULT_RSN,
        help=f'OSRS username for the initial sync (default: "{DEFAULT_RSN}")',
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"local port to serve on (default: {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="do not open the page in a browser on start",
    )
    return parser


def main():
    args = build_arg_parser().parse_args()
    rsn = args.rsn.strip()
    if not rsn:
        print("RSN cannot be empty.", file=sys.stderr)
        return 2

    print(f"pet_wheel local sync server v{__version__}")
    print(f'Running initial sync for "{rsn}"...')
    try:
        snapshot = run_sync(rsn)
        print(f"Initial sync ok: {len(snapshot['owned_item_ids'])} owned item(s) cached.")
    except ValueError as exc:
        print(f"Initial sync failed: {exc}", file=sys.stderr)
        print("Serving anyway; use the page's Sync account button to retry.", file=sys.stderr)

    handler_cls = functools.partial(SyncRequestHandler, directory=str(APP_DIR))
    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", args.port), handler_cls)
    except OSError as exc:
        print(f"Could not start server on 127.0.0.1:{args.port}: {exc}", file=sys.stderr)
        return 1

    page_url = f"http://127.0.0.1:{args.port}/pet-wheel.html"
    # Include ?rsn=... so a first-ever run opens with the account already
    # selected and auto-syncing -- no manual RSN typing needed either.
    url = f"{page_url}?rsn={urllib.parse.quote(rsn)}"
    print(f"Serving {APP_DIR} at {page_url}")
    print("Press Ctrl+C to stop.")

    if not args.no_open:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
