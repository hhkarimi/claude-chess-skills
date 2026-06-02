# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Fetch a chess.com player's most recent games via the public Published-Data API.

No authentication required — the API serves public game archives. We resolve the
player's monthly archive list, walk it newest-first, and collect games until we
have the requested count (default 100). Output is a single games.json the analyzer
consumes.

Usage:
    uv run fetch_games.py <username> [--count 100] [--out /tmp/chess]

The username is a CLI argument and is never stored on disk beyond the output
files (which .gitignore excludes). Pass it fresh each run.
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API_BASE = "https://api.chess.com/pub"
# chess.com's Cloudflare edge rejects the default urllib User-Agent. A real-ish
# UA with a contact string is the documented courtesy.
USER_AGENT = "claude-chess-skills/0.1 (https://github.com/hhkarimi/claude-chess-skills)"


def _get_json(url: str, *, retries: int = 3) -> dict:
    """GET a URL and parse JSON, retrying on transient 429/5xx."""
    last_err: Exception | None = None
    for attempt in range(retries):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code == 404:
                raise
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(2 * (attempt + 1))
                continue
            raise
        except urllib.error.URLError as e:
            last_err = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"GET failed after {retries} attempts: {url} ({last_err})")


def _normalize_result(raw: str) -> str:
    """Map a chess.com per-color result code to win / loss / draw."""
    if raw == "win":
        return "win"
    draws = {
        "agreed",
        "repetition",
        "stalemate",
        "insufficient",
        "50move",
        "timevsinsufficient",
    }
    if raw in draws:
        return "draw"
    # everything else (checkmated, resigned, timeout, abandoned, lose, ...) is a loss
    return "loss"


def _shape_game(game: dict, username: str, index: int) -> dict | None:
    """Reduce a raw chess.com game object to the fields the analyzer needs."""
    pgn = game.get("pgn")
    if not pgn:
        return None  # daily puzzles / unfinished games occasionally lack PGN
    white = game.get("white", {})
    black = game.get("black", {})
    uname_lc = username.lower()
    if white.get("username", "").lower() == uname_lc:
        my_color, me, opp = "white", white, black
    elif black.get("username", "").lower() == uname_lc:
        my_color, me, opp = "black", black, white
    else:
        return None  # username not in this game (shouldn't happen)

    accuracies = game.get("accuracies") or {}
    return {
        "index": index,
        "url": game.get("url"),
        "end_time": game.get("end_time"),
        "time_class": game.get("time_class"),
        "time_control": game.get("time_control"),
        "rated": game.get("rated"),
        "rules": game.get("rules"),
        "eco": game.get("eco"),
        "my_color": my_color,
        "my_rating": me.get("rating"),
        "opp_username": opp.get("username"),
        "opp_rating": opp.get("rating"),
        "my_result_raw": me.get("result"),
        "result": _normalize_result(me.get("result", "")),
        "my_accuracy": accuracies.get(my_color),
        "opp_accuracy": accuracies.get("black" if my_color == "white" else "white"),
        "pgn": pgn,
    }


def fetch_recent_games(username: str, count: int) -> list[dict]:
    archives_url = f"{API_BASE}/player/{username.lower()}/games/archives"
    try:
        archives = _get_json(archives_url).get("archives", [])
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise SystemExit(
                f"chess.com has no public profile for '{username}'. "
                "Check the spelling (it must be the exact chess.com username)."
            )
        raise

    if not archives:
        raise SystemExit(f"'{username}' has no public game archives.")

    collected: list[dict] = []
    # archives are oldest-first; walk newest-first
    for archive_url in reversed(archives):
        month = _get_json(archive_url).get("games", [])
        # within a month, games are oldest-first; reverse for newest-first
        for game in reversed(month):
            shaped = _shape_game(game, username, index=len(collected))
            if shaped is not None:
                collected.append(shaped)
            if len(collected) >= count:
                return collected
        time.sleep(0.3)  # be polite between monthly archive calls
    return collected


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("username", help="chess.com username (exact)")
    ap.add_argument(
        "--count", type=int, default=100, help="number of recent games (default 100)"
    )
    ap.add_argument(
        "--out", default="/tmp/chess", help="output directory (default /tmp/chess)"
    )
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(
        f"Fetching up to {args.count} recent games for '{args.username}'...",
        file=sys.stderr,
    )
    games = fetch_recent_games(args.username, args.count)
    if not games:
        raise SystemExit(f"No games with PGNs found for '{args.username}'.")

    payload = {"username": args.username, "count": len(games), "games": games}
    out_file = out_dir / "games.json"
    out_file.write_text(json.dumps(payload, indent=2))

    wins = sum(g["result"] == "win" for g in games)
    losses = sum(g["result"] == "loss" for g in games)
    draws = sum(g["result"] == "draw" for g in games)
    print(
        f"Wrote {len(games)} games to {out_file} (W{wins}/L{losses}/D{draws}).",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
