# /// script
# requires-python = ">=3.11"
# dependencies = ["chess>=1.11"]
# ///
"""Engine-backed analysis of fetched chess.com games.

Reads the games JSON in --in (games-<username>.json from fetch_games.py), runs
each game through Stockfish via python-chess, and emits alongside it:

  - analysis-<username>.json   — per-game, per-move detail for the player's moves
  - aggregate-<username>.json  — summary stats + top blunders, input for the report

Method (one engine eval per position, the efficient sweep):
  For every position p_0..p_n we record Stockfish's evaluation from White's point
  of view. The centipawn loss (CPL) of a move by side S, going p_{i-1} -> p_i, is
  eval(p_{i-1}) - eval(p_i) measured from S's point of view, floored at 0. eval of
  the position *before* the move already reflects best play, so the gap to the
  eval *after* the move played is exactly what that move threw away.

Moves are classified by CPL (lichess-style thresholds, configurable):
  inaccuracy 50-99, mistake 100-299, blunder >= 300.

Stockfish: if the binary is not on PATH, this script installs it with Homebrew
(`brew install stockfish`) unless --no-install is passed. Override the path with
--stockfish.

Usage:
    uv run analyze_games.py [--in ./chess-analysis] [--depth 12] [--max-games N]
                            [--stockfish PATH] [--no-install]
"""

import argparse
import io
import json
import os
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

import chess
import chess.engine
import chess.pgn

# CPL classification thresholds (centipawns).
INACCURACY = 50
MISTAKE = 100
BLUNDER = 300
# Evals beyond this magnitude (incl. forced mate) are clamped, so a single
# catastrophe doesn't dominate average CPL.
EVAL_CAP = 2000
CPL_CAP = 1000  # per-move CPL ceiling for averaging


def find_games_file(in_dir: Path) -> Path:
    """Locate the games JSON in in_dir. Accepts the per-user games-<name>.json
    written by fetch_games.py (and legacy games.json). Errors if absent or
    ambiguous, so a dir holding multiple users can't be analyzed by accident."""
    matches = sorted(in_dir.glob("games*.json"))
    if not matches:
        raise SystemExit(f"No games*.json in {in_dir} — run fetch_games.py first.")
    if len(matches) > 1:
        names = ", ".join(p.name for p in matches)
        raise SystemExit(
            f"Multiple games files in {in_dir} ({names}); point --in at one "
            "user's directory."
        )
    return matches[0]


def ensure_stockfish(explicit: str | None, allow_install: bool) -> str:
    """Return a usable Stockfish path, installing via Homebrew if needed."""
    if explicit:
        if Path(explicit).exists() or shutil.which(explicit):
            return explicit
        raise SystemExit(f"--stockfish path not found: {explicit}")

    found = shutil.which("stockfish")
    if found:
        return found

    if not allow_install:
        raise SystemExit(
            "Stockfish not found on PATH and --no-install was passed.\n"
            "Install it with:  brew install stockfish"
        )

    brew = shutil.which("brew")
    if not brew:
        raise SystemExit(
            "Stockfish not found and Homebrew is unavailable to auto-install it.\n"
            "Install Stockfish manually (https://stockfishchess.org/download/) "
            "and re-run, or pass --stockfish /path/to/stockfish."
        )

    print(
        "Stockfish not found — installing with `brew install stockfish`...",
        file=sys.stderr,
    )
    subprocess.run([brew, "install", "stockfish"], check=True)
    found = shutil.which("stockfish")
    if not found:
        raise SystemExit("brew install completed but `stockfish` is still not on PATH.")
    return found


def clamp_eval(cp: int) -> int:
    return max(-EVAL_CAP, min(EVAL_CAP, cp))


def load_book(path: Path | str) -> set:
    """Load the vendored opening-position EPD set; missing file -> empty set."""
    p = Path(path)
    if not p.exists():
        return set()
    return {
        line.strip()
        for line in p.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }


def opening_line(records: list, book: set) -> list:
    """Truncate a game to its opening definition.

    records: per-ply (san, epd_after, eval_white) in game order.
    Returns [{ply, san, eval}] for plies 1..cutoff, where cutoff is the deepest
    ply whose resulting position (epd_after) is a known book position. Empty when
    no ply is in book. Evals are White-POV centipawns, clamped.
    """
    cutoff = 0
    for i, (_san, epd, _ev) in enumerate(records, start=1):
        if epd in book:
            cutoff = i
    return [
        {"ply": i, "san": san, "eval": clamp_eval(ev)}
        for i, (san, _epd, ev) in enumerate(records[:cutoff], start=1)
    ]


def phase_of(board: chess.Board) -> str:
    """Classify the position as opening / middlegame / endgame.

    Heuristic by non-pawn, non-king material (both colors): the game starts with
    14 such pieces (2N+2B+2R+1Q per side). Endgame once it thins out; opening
    while still early and nearly full.
    """
    npm = 0
    for piece_type in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN):
        npm += len(board.pieces(piece_type, chess.WHITE))
        npm += len(board.pieces(piece_type, chess.BLACK))
    if npm <= 6:
        return "endgame"
    if board.fullmove_number <= 10 and npm >= 12:
        return "opening"
    return "middlegame"


def base_seconds(time_control: str | None) -> int | None:
    """Parse a chess.com time_control string ('600', '600+5', '1/259200') to base seconds."""
    if not time_control:
        return None
    if "/" in time_control:  # daily games, e.g. "1/259200"
        return None
    head = time_control.split("+", 1)[0]
    try:
        return int(head)
    except ValueError:
        return None


def classify(cpl: int) -> str | None:
    if cpl >= BLUNDER:
        return "blunder"
    if cpl >= MISTAKE:
        return "mistake"
    if cpl >= INACCURACY:
        return "inaccuracy"
    return None


def analyze_game(
    engine: chess.engine.SimpleEngine,
    game_meta: dict,
    depth: int,
    book: set | None = None,
) -> dict | None:
    """Analyze one game; return per-move detail for the player's moves."""
    pgn_game = chess.pgn.read_game(io.StringIO(game_meta["pgn"]))
    if pgn_game is None:
        return None

    my_color = chess.WHITE if game_meta["my_color"] == "white" else chess.BLACK
    headers = pgn_game.headers
    base = base_seconds(headers.get("TimeControl") or game_meta.get("time_control"))
    # time trouble: under 30s, or under 10% of base time, whichever is larger
    tt_threshold = max(30.0, 0.10 * base) if base else 30.0

    limit = chess.engine.Limit(depth=depth)

    # Walk the mainline, recording (board-before, move, clock-after) per ply.
    nodes = list(pgn_game.mainline())
    board = pgn_game.board()

    # eval of the initial position from White's POV
    evals: list[int] = [_eval_white(engine, board, limit)]
    move_records = []  # (mover_color, san, fen_before, move_no, phase, clock)
    opening_records: list = []
    for node in nodes:
        move = node.move
        mover = board.turn
        san = board.san(move)
        fen_before = board.fen()
        move_no = board.fullmove_number
        ph = phase_of(board)
        clk = node.clock()  # seconds remaining for mover after this move, or None
        board.push(move)
        evals.append(_eval_white(engine, board, limit))
        opening_records.append((san, board.epd(), evals[-1]))
        move_records.append((mover, san, fen_before, move_no, ph, clk))

    moves_out = []
    for i, (mover, san, fen_before, move_no, ph, clk) in enumerate(move_records):
        if mover != my_color:
            continue
        before_w, after_w = evals[i], evals[i + 1]
        # convert to mover's POV
        sign = 1 if mover == chess.WHITE else -1
        best = sign * before_w
        actual = sign * after_w
        raw_loss = best - actual
        cpl = max(0, min(CPL_CAP, raw_loss))
        in_tt = clk is not None and clk <= tt_threshold
        moves_out.append(
            {
                "move_no": move_no,
                "san": san,
                "phase": ph,
                "cpl": cpl,
                "raw_swing": max(0, raw_loss),
                "class": classify(cpl),
                "in_time_trouble": in_tt,
                "clock": clk,
                "eval_before": sign * clamp_eval(before_w),
                "eval_after": sign * clamp_eval(after_w),
                "fen_before": fen_before,
            }
        )

    return {
        "index": game_meta["index"],
        "url": game_meta["url"],
        "my_color": game_meta["my_color"],
        "result": game_meta["result"],
        "my_result_raw": game_meta["my_result_raw"],
        "time_class": game_meta["time_class"],
        "my_rating": game_meta["my_rating"],
        "opp_rating": game_meta["opp_rating"],
        "my_accuracy": game_meta["my_accuracy"],
        "eco": headers.get("ECO"),
        "opening": _opening_name(headers),
        "moves": moves_out,
        "opening_line": opening_line(opening_records, book or set()),
    }


def _eval_white(engine: chess.engine.SimpleEngine, board: chess.Board, limit) -> int:
    if board.is_game_over():
        # terminal: settle the eval from the result so the last move is scored
        outcome = board.outcome()
        if outcome is None or outcome.winner is None:
            return 0
        return EVAL_CAP if outcome.winner == chess.WHITE else -EVAL_CAP
    info = engine.analyse(board, limit)
    return clamp_eval(info["score"].white().score(mate_score=EVAL_CAP))


def _opening_name(headers) -> str:
    url = headers.get("ECOUrl", "")
    if url:
        slug = url.rstrip("/").rsplit("/", 1)[-1]
        return slug.replace("-", " ")
    return headers.get("ECO", "Unknown")


def build_aggregate(per_game: list[dict], top_n: int = 12) -> dict:
    results = Counter(g["result"] for g in per_game)
    by_color = defaultdict(Counter)
    by_time_class = Counter(g["time_class"] for g in per_game)

    cpl_by_phase = defaultdict(list)
    class_by_phase = defaultdict(Counter)
    cpl_by_result = defaultdict(list)
    tt_moves = 0
    tt_blunders = 0
    total_my_moves = 0
    blunders = mistakes = inaccuracies = 0
    opening_perf = defaultdict(
        lambda: {"win": 0, "loss": 0, "draw": 0, "opening_cpl": []}
    )
    all_blunders = []
    tt_loss_games = 0

    for g in per_game:
        by_color[g["my_color"]][g["result"]] += 1
        opening_key = (g["opening"], g["my_color"])
        opening_perf[opening_key][g["result"]] += 1
        game_had_tt_blunder = False
        for m in g["moves"]:
            total_my_moves += 1
            cpl_by_phase[m["phase"]].append(m["cpl"])
            cpl_by_result[g["result"]].append(m["cpl"])
            if m["phase"] == "opening":
                opening_perf[opening_key]["opening_cpl"].append(m["cpl"])
            if m["in_time_trouble"]:
                tt_moves += 1
            cls = m["class"]
            if cls:
                class_by_phase[m["phase"]][cls] += 1
            if cls == "blunder":
                blunders += 1
                if m["in_time_trouble"]:
                    tt_blunders += 1
                    game_had_tt_blunder = True
                all_blunders.append(
                    {
                        "game_url": g["url"],
                        "color": g["my_color"],
                        "result": g["result"],
                        "move_no": m["move_no"],
                        "san": m["san"],
                        "phase": m["phase"],
                        "cpl": m["cpl"],
                        "raw_swing": m["raw_swing"],
                        "eval_before": m["eval_before"],
                        "eval_after": m["eval_after"],
                        "in_time_trouble": m["in_time_trouble"],
                        "fen_before": m["fen_before"],
                    }
                )
            elif cls == "mistake":
                mistakes += 1
            elif cls == "inaccuracy":
                inaccuracies += 1
        if game_had_tt_blunder and g["result"] == "loss":
            tt_loss_games += 1

    def avg(xs):
        return round(sum(xs) / len(xs), 1) if xs else None

    n_games = len(per_game)
    accuracies = [g["my_accuracy"] for g in per_game if g["my_accuracy"] is not None]

    # opening summary: only repertoire lines seen 2+ times, sorted by games desc
    opening_summary = []
    for (opening, color), rec in opening_perf.items():
        played = rec["win"] + rec["loss"] + rec["draw"]
        if played < 2:
            continue
        opening_summary.append(
            {
                "opening": opening,
                "color": color,
                "games": played,
                "win": rec["win"],
                "loss": rec["loss"],
                "draw": rec["draw"],
                "avg_opening_cpl": avg(rec["opening_cpl"]),
            }
        )
    opening_summary.sort(key=lambda r: (-r["games"], r["opening"]))

    all_blunders.sort(key=lambda b: -b["raw_swing"])

    return {
        "games_analyzed": n_games,
        "results": dict(results),
        "by_color": {c: dict(v) for c, v in by_color.items()},
        "by_time_class": dict(by_time_class),
        "chesscom_avg_accuracy": avg(accuracies),
        "total_my_moves": total_my_moves,
        "move_quality": {
            "blunders": blunders,
            "mistakes": mistakes,
            "inaccuracies": inaccuracies,
            "blunders_per_game": round(blunders / n_games, 2) if n_games else None,
            "mistakes_per_game": round(mistakes / n_games, 2) if n_games else None,
        },
        "avg_cpl_overall": avg([c for xs in cpl_by_phase.values() for c in xs]),
        "avg_cpl_by_phase": {ph: avg(xs) for ph, xs in cpl_by_phase.items()},
        "blunders_by_phase": {ph: dict(c) for ph, c in class_by_phase.items()},
        "avg_cpl_by_result": {res: avg(xs) for res, xs in cpl_by_result.items()},
        "time_trouble": {
            "my_moves_in_time_trouble": tt_moves,
            "blunders_in_time_trouble": tt_blunders,
            "losses_with_time_trouble_blunder": tt_loss_games,
            "share_of_blunders_in_time_trouble": (
                round(tt_blunders / blunders, 2) if blunders else None
            ),
        },
        "opening_performance": opening_summary,
        "top_blunders": all_blunders[:top_n],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--in",
        dest="in_dir",
        default="chess-analysis",
        help="dir with games-<username>.json (e.g. chess-analysis/<username>)",
    )
    ap.add_argument(
        "--depth", type=int, default=12, help="Stockfish search depth (default 12)"
    )
    ap.add_argument(
        "--max-games", type=int, default=None, help="limit games (for quick runs)"
    )
    ap.add_argument("--stockfish", default=None, help="path to stockfish binary")
    ap.add_argument(
        "--no-install", action="store_true", help="do not auto-install Stockfish"
    )
    args = ap.parse_args()

    in_dir = Path(args.in_dir)
    games_file = find_games_file(in_dir)

    data = json.loads(games_file.read_text())
    games = data["games"]
    username = data.get("username", "")
    suffix = f"-{username}" if username else ""
    if args.max_games:
        games = games[: args.max_games]

    sf_path = ensure_stockfish(args.stockfish, allow_install=not args.no_install)
    engine = chess.engine.SimpleEngine.popen_uci(sf_path)
    try:
        engine.configure({"Threads": os.cpu_count() or 1, "Hash": 128})
    except chess.engine.EngineError:
        pass

    book = load_book(Path(__file__).parent / "openings_book.txt")
    per_game = []
    try:
        for n, g in enumerate(games, 1):
            print(
                f"  [{n}/{len(games)}] analyzing game {g['index']}...", file=sys.stderr
            )
            result = analyze_game(engine, g, args.depth, book)
            if result:
                per_game.append(result)
    finally:
        engine.quit()

    aggregate = build_aggregate(per_game)

    analysis_file = in_dir / f"analysis{suffix}.json"
    aggregate_file = in_dir / f"aggregate{suffix}.json"
    analysis_file.write_text(json.dumps(per_game, indent=2))
    aggregate_file.write_text(json.dumps(aggregate, indent=2))
    print(
        f"Analyzed {len(per_game)} games. Wrote {analysis_file} and {aggregate_file}.",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
