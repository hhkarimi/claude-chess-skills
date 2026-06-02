# /// script
# requires-python = ">=3.11"
# dependencies = ["chess>=1.11"]
# ///
"""Render aggregate.json + analysis.json as a self-contained HTML report.

One file, no CDN, no JS library: inline CSS, hand-rolled inline SVG charts, and
chess board diagrams via python-chess (chess.svg). Claude can optionally pass a
Markdown file of coaching prose with --tips, injected as "Coach's notes".

Usage:
    uv run render_report.py [--in ./chess-analysis] [--tips tips.md]
"""

import argparse
import html
import io
import json
import re
from pathlib import Path

import chess
import chess.pgn
import chess.svg

DEFAULT_DIR = "chess-analysis"

STYLE = """
body { font-family: -apple-system, Segoe UI, Roboto, sans-serif; margin: 2rem auto;
       max-width: 960px; color: #1a1a1a; line-height: 1.45; }
h1, h2, h3 { line-height: 1.2; }
table { border-collapse: collapse; width: 100%; margin: 0.5rem 0 1.5rem; }
th, td { border: 1px solid #ddd; padding: 6px 10px; text-align: left; }
th { background: #f4f4f4; }
.num { text-align: right; }
.chart { margin: 0.5rem 0 1.75rem; }
.board { display: inline-block; vertical-align: top; margin: 4px 12px 4px 0; }
.card { border: 1px solid #e2e2e2; border-radius: 8px; padding: 12px 16px; margin: 10px 0; }
.coach { background: #fffdf2; border-color: #e9dca0; }
.muted { color: #666; }
svg { max-width: 100%; height: auto; }
.term { text-decoration: underline dotted; cursor: help; }
.term a { color: inherit; text-decoration: none; }
.player { display: inline-block; vertical-align: top; margin: 4px 12px 4px 0; }
.player .controls { margin-top: 4px; text-align: center; }
.player .controls button { font-size: 14px; margin: 0 2px; cursor: pointer; }
.player .cap { display: inline-block; min-width: 6em; font-variant-numeric: tabular-nums; }
.glossary dt { font-weight: 600; margin-top: 6px; }
"""


BOARD_SCRIPT = """<script>
function chessStep(id, step) {
  var w = document.getElementById(id);
  var frames = w.querySelectorAll('.frame');
  var n = frames.length;
  var i = parseInt(w.dataset.idx, 10) || 0;
  if (step === 'first') i = 0;
  else if (step === 'last') i = n - 1;
  else i = Math.max(0, Math.min(n - 1, i + step));
  for (var k = 0; k < n; k++) { frames[k].hidden = (k !== i); }
  w.dataset.idx = i;
  w.querySelector('.cap').textContent = frames[i].getAttribute('data-cap');
}
</script>"""

_widget_seq = 0


def _esc(s: object) -> str:
    return html.escape(str(s))


def _move_str(b: dict) -> str:
    """Format a blunder's move like White '20. Qxf7' or Black '20...Qxf7'."""
    sep = ". " if b.get("color") == "white" else "..."
    return f"{b.get('move_no')}{sep}{b.get('san')}"


def _cpl_str(cpl: float | None) -> str:
    """Centipawn-loss value rounded for display, or '-' when absent."""
    return f"{cpl:.0f}" if cpl is not None else "-"


def _cp_pawns(cp_white: int) -> str:
    """Format a White-POV centipawn score as signed pawns, e.g. +0.3 / -1.2."""
    return f"{cp_white / 100:+.1f}"


GLOSSARY = {
    "cpl": (
        "CPL",
        "Centipawn loss: how much worse your move was than the engine's best "
        "move, in hundredths of a pawn. Lower is better.",
    ),
    "blunder": (
        "blunder",
        "A move that throws away a lot — here, 300 or more centipawns versus the "
        "best move.",
    ),
    "mistake": (
        "mistake",
        "A move that loses a moderate amount, 100 to 299 centipawns.",
    ),
    "inaccuracy": (
        "inaccuracy",
        "A small slip, 50 to 99 centipawns worse than the best move.",
    ),
    "time_trouble": (
        "time trouble",
        "Moves made with little time left on your clock, where mistakes are more "
        "likely.",
    ),
    "eval": (
        "evaluation",
        "The engine's score for a position in centipawns (100 = one pawn). "
        "Positive means you are better.",
    ),
    "phase": (
        "phase",
        "Which stage of the game a move is in: opening, middlegame, or endgame.",
    ),
}


def _term(key: str) -> str:
    """Wrap a glossary term in a tooltip + link to its glossary entry."""
    display, definition = GLOSSARY[key]
    return (
        f'<abbr class="term" title="{_esc(definition)}">'
        f'<a href="#glossary-{key}">{_esc(display)}</a></abbr>'
    )


def section_glossary() -> str:
    items = "".join(
        f'<dt id="glossary-{key}">{_esc(display)}</dt><dd>{_esc(defn)}</dd>'
        for key, (display, defn) in GLOSSARY.items()
    )
    return '<h2 id="glossary">Glossary</h2>\n<dl class="glossary">' + items + "</dl>"


def svg_bars(
    rows: list[tuple[str, float]],
    *,
    unit: str = "",
    color: str = "#3b6ea5",
    width: int = 720,
) -> str:
    """Horizontal bar chart as inline SVG. rows = [(label, value), ...].

    Rows with a None value are skipped; zero values render a label with no bar.
    """
    rows = [(lab, v) for lab, v in rows if v is not None]
    if not rows:
        return '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"></svg>'
    row_h, pad_r, top = 28, 70, 8
    # Size the label column to the longest label (~7px/char at 13px) so long
    # labels like the blunder-origin rows aren't overdrawn by the bars.
    longest = max(len(lab) for lab, _ in rows)
    pad_l = min(width // 2, max(130, longest * 7 + 12))
    max_v = max((v for _, v in rows), default=0) or 1
    bar_area = width - pad_l - pad_r
    height = top * 2 + row_h * len(rows)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" role="img">'
    ]
    for i, (label, v) in enumerate(rows):
        y = top + i * row_h
        cy = y + row_h // 2
        parts.append(f'<text x="0" y="{cy + 4}" font-size="13">{_esc(label)}</text>')
        bw = round(bar_area * v / max_v)
        if v > 0:
            bw = max(2, bw)
            parts.append(
                f'<rect x="{pad_l}" y="{y + 5}" width="{bw}" '
                f'height="{row_h - 12}" rx="3" fill="{color}"></rect>'
            )
        val = f"{v:g}{unit}"
        parts.append(
            f'<text x="{pad_l + (bw if v > 0 else 0) + 8}" y="{cy + 4}" '
            f'font-size="12" fill="#333">{_esc(val)}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def _chart(title: str, svg: str) -> str:
    return f'<div class="chart"><h3>{_esc(title)}</h3>{svg}</div>'


def section_charts(agg: dict) -> str:
    by_color = agg.get("by_color", {})
    res = agg.get("results", {})
    results_rows = [
        ("Wins", res.get("win", 0)),
        ("Losses", res.get("loss", 0)),
        ("Draws", res.get("draw", 0)),
    ]
    phase = agg.get("avg_cpl_by_phase", {})
    phase_rows = [
        (p.title(), phase.get(p)) for p in ("opening", "middlegame", "endgame")
    ]
    mq = agg.get("move_quality", {})
    mq_rows = [
        ("Blunders", mq.get("blunders", 0)),
        ("Mistakes", mq.get("mistakes", 0)),
        ("Inaccuracies", mq.get("inaccuracies", 0)),
    ]
    r = agg.get("avg_cpl_by_result", {})
    res_rows = [
        ("In wins", r.get("win")),
        ("In losses", r.get("loss")),
        ("In draws", r.get("draw")),
    ]
    tt = agg.get("time_trouble", {})
    share = tt.get("share_of_blunders_in_time_trouble")
    share_str = f"{100 * share:.0f}%" if share is not None else "-"
    w = by_color.get("white", {})
    b = by_color.get("black", {})
    color_table = (
        "<table><tr><th>Color</th><th class='num'>W</th><th class='num'>L</th>"
        "<th class='num'>D</th></tr>"
        f"<tr><td>White</td><td class='num'>{w.get('win', 0)}</td>"
        f"<td class='num'>{w.get('loss', 0)}</td><td class='num'>{w.get('draw', 0)}</td></tr>"
        f"<tr><td>Black</td><td class='num'>{b.get('win', 0)}</td>"
        f"<td class='num'>{b.get('loss', 0)}</td><td class='num'>{b.get('draw', 0)}</td></tr>"
        "</table>"
    )
    return "\n".join(
        [
            "<h2>Charts</h2>",
            _chart("Results by color", svg_bars(results_rows)),
            color_table,
            _chart(
                "Average centipawn loss by phase (lower is better)",
                svg_bars(phase_rows, unit=" cpl", color="#a5563b"),
            ),
            _chart("Move quality", svg_bars(mq_rows, color="#7a3ba5")),
            _chart(
                "Average centipawn loss — wins vs losses",
                svg_bars(res_rows, unit=" cpl", color="#3b8aa5"),
            ),
            "<h3>Time trouble</h3>",
            '<ul class="muted">'
            f"<li>Moves in time trouble: {tt.get('my_moves_in_time_trouble', 0)}</li>"
            f"<li>Blunders in time trouble: {tt.get('blunders_in_time_trouble', 0)} "
            f"({share_str} of all blunders)</li>"
            f"<li>Losses with a time-trouble blunder: "
            f"{tt.get('losses_with_time_trouble_blunder', 0)}</li></ul>",
        ]
    )


def blunder_origin_buckets(games: list) -> dict:
    """Count blunders by the player-POV eval *before* the blunder move.

    analysis.json already stores eval_before/eval_after in the mover's POV
    (see analyze_games.py), so no further sign flip is needed here.
    """
    out = {"winning": 0, "equal": 0, "losing": 0}
    for g in games:
        for m in g.get("moves", []):
            if m.get("class") != "blunder":
                continue
            e = m.get("eval_before", 0)
            if e > 150:
                out["winning"] += 1
            elif e < -150:
                out["losing"] += 1
            else:
                out["equal"] += 1
    return out


def section_blunder_origin(games: list) -> str:
    b = blunder_origin_buckets(games)
    total = sum(b.values()) or 1
    rows = [
        (f"From winning (>+1.5): {100 * b['winning'] // total}%", b["winning"]),
        (f"From equal (±1.5): {100 * b['equal'] // total}%", b["equal"]),
        (f"From losing (<-1.5): {100 * b['losing'] // total}%", b["losing"]),
    ]
    return "\n".join(
        [
            "<h2>Where your blunders come from</h2>",
            '<p class="muted">Each blunder bucketed by the engine '
            f"{_term('eval')} (your point of view) on the move just before it. "
            "Blunders thrown from winning or equal positions are the ones you can "
            "most directly stop.</p>",
            _chart(
                "Blunders by position strength before the mistake",
                svg_bars(rows, color="#b5482f"),
            ),
        ]
    )


def eval_series(game: dict) -> list:
    """Player-POV eval after each of the player's moves, in order.

    analysis.json already stores eval_after in the mover's POV, so the values
    are used as-is.
    """
    return [m.get("eval_after", 0) for m in game.get("moves", [])]


def svg_sparkline(
    values: list, *, mark_index: int | None = None, width: int = 320, height: int = 70
) -> str:
    """A small eval line. y is clamped to ±1000cp so one blowup doesn't flatten it."""
    if not values:
        return '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"></svg>'
    cap = 1000
    clamped = [max(-cap, min(cap, v)) for v in values]
    n = len(clamped)
    pad = 6

    def x(i: int) -> float:
        return pad + (width - 2 * pad) * (i / (n - 1) if n > 1 else 0)

    def y(v: float) -> float:
        return pad + (height - 2 * pad) * (1 - (v + cap) / (2 * cap))

    pts = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(clamped))
    mid = y(0)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
        f'<line x1="{pad}" y1="{mid:.1f}" x2="{width - pad}" y2="{mid:.1f}" '
        'stroke="#ccc" stroke-dasharray="3 3"></line>',
        f'<polyline fill="none" stroke="#3b6ea5" stroke-width="2" points="{pts}"></polyline>',
    ]
    if mark_index is not None and 0 <= mark_index < n:
        parts.append(
            f'<circle cx="{x(mark_index):.1f}" cy="{y(clamped[mark_index]):.1f}" '
            'r="4" fill="#b5482f"></circle>'
        )
    parts.append("</svg>")
    return "".join(parts)


def opening_position_fen(game: dict) -> str | None:
    """FEN once the opening is complete: the first non-opening move's fen_before,
    else the last move's fen_before, else None."""
    moves = game.get("moves", [])
    for m in moves:
        if m.get("phase") != "opening":
            return m.get("fen_before")
    if moves:
        return moves[-1].get("fen_before")
    return None


def board_svg(fen: str, *, color: str = "white", size: int = 240) -> str:
    """Inline SVG board for a FEN, oriented from the given color's side."""
    orientation = chess.WHITE if color == "white" else chess.BLACK
    return chess.svg.board(
        chess.Board(fen), orientation=orientation, size=size, coordinates=False
    )


def board_player(frames: list, *, orient: str = "white", size: int = 240) -> str:
    """Interactive stepper from frames=[(fen, caption), ...]. Empty list -> ''.

    Pre-renders one inline SVG per frame; only the first is visible. The shared
    BOARD_SCRIPT (emitted once by build_html) steps between frames. Self-contained.
    """
    global _widget_seq
    if not frames:
        return ""
    _widget_seq += 1
    wid = f"bp{_widget_seq}"
    orientation = chess.WHITE if orient == "white" else chess.BLACK
    divs = []
    for i, (fen, cap) in enumerate(frames):
        svg = chess.svg.board(
            chess.Board(fen), orientation=orientation, size=size, coordinates=False
        )
        hidden = "" if i == 0 else " hidden"
        divs.append(f'<div class="frame"{hidden} data-cap="{_esc(cap)}">{svg}</div>')
    controls = (
        '<div class="controls">'
        f"<button onclick=\"chessStep('{wid}','first')\">&#9198;</button>"
        f"<button onclick=\"chessStep('{wid}',-1)\">&#9664;</button>"
        f'<span class="cap">{_esc(frames[0][1])}</span>'
        f"<button onclick=\"chessStep('{wid}',1)\">&#9654;</button>"
        f"<button onclick=\"chessStep('{wid}','last')\">&#9197;</button>"
        "</div>"
    )
    return (
        f'<div class="player board" id="{wid}" data-idx="0">'
        f'<div class="frames">{"".join(divs)}</div>{controls}</div>'
    )


def opening_frames(opening_line: list) -> list:
    """Frames for an opening stepper from analysis.json's opening_line.

    Replays the SANs from the start position; each move frame's caption is the
    move plus its White-POV CP score. Returns [(fen, caption)]; stops early on an
    unreplayable SAN.
    """
    board = chess.Board()
    frames = [(board.fen(), "start")]
    for entry in opening_line:
        san = entry.get("san", "")
        num = board.fullmove_number
        sep = ". " if board.turn == chess.WHITE else "..."
        try:
            board.push_san(san)
        except ValueError:
            break
        frames.append(
            (board.fen(), f"{num}{sep}{san}  {_cp_pawns(entry.get('eval', 0))}")
        )
    return frames


def game_frames(pgn: str, *, start_ply: int, end_ply: int) -> list:
    """Replay PGN and return [(fen, caption)] for plies in [start_ply, end_ply].

    Caption is the move in '<num>. <san>' (white) or '<num>...<san>' (black) form.
    When start_ply == 0, frame 0 is the initial position captioned 'start'.
    """
    game = chess.pgn.read_game(io.StringIO(pgn))
    if game is None:
        return []
    board = game.board()
    frames = []
    if start_ply == 0:
        frames.append((board.fen(), "start"))
    ply = 0
    for move in game.mainline_moves():
        ply += 1
        san = board.san(move)
        num = board.fullmove_number
        sep = ". " if board.turn == chess.WHITE else "..."
        board.push(move)
        if start_ply <= ply <= end_ply:
            frames.append((board.fen(), f"{num}{sep}{san}"))
    return frames


def _position_key(fen: str) -> str:
    """Piece placement + side + castling + en passant (FEN minus move counters)."""
    return " ".join(fen.split()[:4])


def _opening_end_ply(pgn: str, target_fen: str | None, cap: int = 20) -> int:
    """Ply at which the PGN first reaches target_fen (position-only), else cap."""
    game = chess.pgn.read_game(io.StringIO(pgn))
    if game is None:
        return cap
    board = game.board()
    target = _position_key(target_fen) if target_fen else None
    ply = 0
    for move in game.mainline_moves():
        ply += 1
        board.push(move)
        if target is not None and _position_key(board.fen()) == target:
            return ply
        if ply >= cap:
            break
    return min(ply, cap)


def _blunder_ply(pgn: str, move_no: int, color: str, san: str) -> int | None:
    """1-based ply of the move matching fullmove number + side + SAN, else None."""
    game = chess.pgn.read_game(io.StringIO(pgn))
    if game is None:
        return None
    board = game.board()
    want_white = color == "white"
    ply = 0
    for move in game.mainline_moves():
        ply += 1
        played = board.san(move)
        match = (
            board.fullmove_number == move_no
            and (board.turn == chess.WHITE) == want_white
            and played == san
        )
        board.push(move)
        if match:
            return ply
    return None


def _find_opening_game(games: list, opening: str, color: str) -> dict | None:
    for g in games:
        if g.get("opening") == opening and g.get("my_color") == color:
            return g
    return None


def _board_html(frames: list, fen: str | None, color: str) -> str:
    """Interactive stepper when frames exist, else a static board, else ''."""
    if frames:
        return board_player(frames, orient=color)
    if fen:
        return f'<div class="board">{board_svg(fen, color=color)}</div>'
    return ""


def section_openings(
    agg: dict, games: list, pgn_by_url: dict | None = None, limit: int = 8
) -> str:
    pgn_by_url = pgn_by_url or {}
    ops = agg.get("opening_performance", [])
    if not ops:
        return (
            "<h2>Openings</h2>"
            "<p class='muted'>(no opening played 2+ times in this sample)</p>"
        )
    cards = []
    for o in ops[:limit]:
        rec = f"{o['win']}-{o['loss']}-{o['draw']}"
        wr = f"{100 * o['win'] / o['games']:.0f}%" if o.get("games") else "-"
        cpl_str = _cpl_str(o.get("avg_opening_cpl"))
        g = _find_opening_game(games, o["opening"], o["color"])
        fen = opening_position_fen(g) if g else None
        ol = g.get("opening_line") if g else None
        pgn = pgn_by_url.get(g.get("url")) if g else None
        if ol:
            frames = opening_frames(ol)
        elif pgn:
            frames = game_frames(pgn, start_ply=0, end_ply=_opening_end_ply(pgn, fen))
        else:
            frames = []
        board = _board_html(frames, fen, o["color"])
        cards.append(
            '<div class="card">'
            f"<h3>{_esc(o['opening'])} <span class='muted'>"
            f"({_esc(o['color'].title())})</span></h3>"
            f"{board}"
            "<div>"
            f"<p>Record: <strong>{_esc(rec)}</strong> · Win rate: {_esc(wr)} · "
            f"Opening {_term('cpl')}: {_esc(cpl_str)}</p></div></div>"
        )
    note = (
        '<p class="muted">Each board steps through the moves that define the '
        "opening; the number after each move is the engine score in pawns from "
        "White's point of view (+ = White is better).</p>"
    )
    return "<h2>Openings</h2>\n" + note + "\n" + "\n".join(cards)


def section_top_blunders(
    agg: dict, pgn_by_url: dict | None = None, games: list | None = None, limit: int = 8
) -> str:
    pgn_by_url = pgn_by_url or {}
    by_url = {g.get("url"): g for g in (games or [])}
    blunders = agg.get("top_blunders", [])
    if not blunders:
        return "<h2>Top blunders</h2><p class='muted'>(no blunders found)</p>"
    cards = []
    for b in blunders[:limit]:
        move = _move_str(b)
        url = b.get("game_url") or ""
        # eval-swing sparkline for this game, with the blunder move marked
        spark = ""
        g = by_url.get(url)
        if g:
            idx = next(
                (
                    i
                    for i, m in enumerate(g.get("moves", []))
                    if m.get("move_no") == b.get("move_no")
                ),
                None,
            )
            spark = svg_sparkline(eval_series(g), mark_index=idx)
        pgn = pgn_by_url.get(url)
        frames = []
        if pgn:
            ply = _blunder_ply(pgn, b.get("move_no"), b.get("color"), b.get("san"))
            if ply:
                frames = game_frames(pgn, start_ply=max(1, ply - 4), end_ply=ply + 1)
        board = _board_html(frames, b.get("fen_before"), b.get("color", "white"))
        link = f'<a href="{_esc(url)}">replay on chess.com</a>' if url else ""
        cards.append(
            '<div class="card">'
            f"<h3>{_esc(move)} "
            f"<span class='muted'>· swing {_esc(b.get('raw_swing'))}cp</span></h3>"
            f"{spark}"
            f"{board}"
            "<div>"
            f"<p>{_esc(b.get('phase'))} · {_esc(b.get('color'))} · "
            f"{_esc(b.get('result'))}</p>"
            f"<p>{link}</p></div></div>"
        )
    return "\n".join(
        [
            "<h2>Top blunders</h2>",
            '<p class="muted">Each card shows the evaluation swing for that game '
            "(your point of view) with the blunder marked, then the board. Step "
            "through the last few moves into the blunder, or open it on chess.com.</p>",
            *cards,
        ]
    )


def md_to_html(text: str) -> str:
    """Minimal Markdown -> HTML: #/##/### headings, '- ' bullets, blank-line
    paragraphs, and **bold**. Everything is HTML-escaped first."""
    blocks, lines, bullets = [], text.splitlines(), []

    def flush_bullets() -> None:
        if bullets:
            blocks.append("<ul>" + "".join(f"<li>{x}</li>" for x in bullets) + "</ul>")
            bullets.clear()

    def inline(s: str) -> str:
        return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", _esc(s))

    para: list[str] = []

    def flush_para() -> None:
        if para:
            blocks.append("<p>" + " ".join(inline(p) for p in para) + "</p>")
            para.clear()

    # Headings are intentionally demoted (# and ## -> h3, ### -> h4) so coaching
    # prose never outranks the report's own <h2> section titles.
    for raw in lines:
        line = raw.rstrip()
        if not line.strip():
            flush_bullets()
            flush_para()
        elif line.startswith("### "):
            flush_bullets()
            flush_para()
            blocks.append(f"<h4>{inline(line[4:])}</h4>")
        elif line.startswith("## "):
            flush_bullets()
            flush_para()
            blocks.append(f"<h3>{inline(line[3:])}</h3>")
        elif line.startswith("# "):
            flush_bullets()
            flush_para()
            blocks.append(f"<h3>{inline(line[2:])}</h3>")
        elif line.lstrip().startswith("- "):
            flush_para()
            bullets.append(inline(line.lstrip()[2:]))
        else:
            para.append(line)
    flush_bullets()
    flush_para()
    return "\n".join(blocks)


def _weak_openings(agg: dict) -> list:
    """Openings worth shoring up: a losing record or a high opening CPL."""
    return [
        o
        for o in agg.get("opening_performance", [])
        if o.get("loss", 0) > o.get("win", 0) or (o.get("avg_opening_cpl") or 0) > 60
    ]


def section_practice(agg: dict) -> str:
    """Tailored lichess practice links chosen from the player's weaknesses."""
    cpl = agg.get("avg_cpl_by_phase", {})
    bbp = agg.get("blunders_by_phase", {})
    ranked = sorted(
        ("opening", "middlegame", "endgame"),
        key=lambda p: (cpl.get(p) or 0) + bbp.get(p, {}).get("blunder", 0) * 10,
        reverse=True,
    )
    items = [
        '<li><a href="https://lichess.org/training">Lichess puzzles</a> — daily '
        "tactics build the habit of checking your opponent's reply before you "
        "move, which is where most blunders are avoided.</li>"
    ]
    if "endgame" in ranked[:2]:
        items.append(
            '<li><a href="https://lichess.org/practice">Lichess practice drills</a> '
            "— the endgame is one of your two leakiest phases; these teach the basic "
            "winning and drawing techniques.</li>"
        )
    weak = _weak_openings(agg)
    if weak:
        worst = sorted(
            weak,
            key=lambda o: (
                o.get("win", 0) - o.get("loss", 0),
                -(o.get("avg_opening_cpl") or 0),
            ),
        )[0]
        items.append(
            '<li><a href="https://lichess.org/opening">Lichess opening explorer</a> '
            f"— look up {_esc(worst['opening'])} ({_esc(worst['color'])}), your "
            "weakest opening, to learn its main lines and plans.</li>"
        )
    return "<h3>Where to practice</h3>\n<ul>" + "".join(items) + "</ul>"


def section_study_plan(agg: dict, tips_md: str | None = None) -> str:
    parts = ["<h2>Study plan</h2>"]
    if tips_md:
        parts.append(
            '<div class="card coach"><h3>Coach\'s notes</h3>'
            + md_to_html(tips_md)
            + "</div>"
        )

    # 1. Rank phases by (avg CPL + blunder count) — biggest leak first.
    cpl = agg.get("avg_cpl_by_phase", {})
    bbp = agg.get("blunders_by_phase", {})
    phases = []
    for p in ("opening", "middlegame", "endgame"):
        bl = bbp.get(p, {}).get("blunder", 0)
        score = (cpl.get(p) or 0) + (bl * 10)
        phases.append((p, score, cpl.get(p), bl))
    phases.sort(key=lambda t: t[1], reverse=True)
    phase_items = "".join(
        f"<li><strong>{p.title()}</strong>: "
        f"avg {_term('cpl')} {('-' if c is None else round(c))}, {bl} blunders</li>"
        for p, _, c, bl in phases
    )
    parts.append(
        "<h3>Phase priorities (worst leak first)</h3><ol>" + phase_items + "</ol>"
    )

    # 2. Weak openings: losing record or opening CPL > 60.
    weak = _weak_openings(agg)
    if weak:
        wk = "".join(
            f"<li>{_esc(o['opening'])} ({_esc(o['color'])}): "
            f"{o['win']}-{o['loss']}-{o['draw']}, "
            f"opening CPL {_cpl_str(o.get('avg_opening_cpl'))}</li>"
            for o in weak
        )
        parts.append("<h3>Openings to shore up</h3><ul>" + wk + "</ul>")

    # 3. Concrete drills from the top blunders.
    drills = agg.get("top_blunders", [])[:5]
    if drills:
        dl = "".join(
            f'<li><a href="{_esc(b.get("game_url", ""))}">{_esc(_move_str(b))}</a></li>'
            for b in drills
        )
        parts.append(
            "<h3>Replay these positions</h3>"
            '<p class="muted">Set each up and find the move you missed.</p>'
            "<ul>" + dl + "</ul>"
        )
    parts.append(section_practice(agg))
    return "\n".join(parts)


def build_html(
    agg: dict, games: list, raw_games: list | None = None, tips_md: str | None = None
) -> str:
    """Assemble the full self-contained HTML document."""
    pgn_by_url = {g.get("url"): g.get("pgn") for g in (raw_games or []) if g.get("pgn")}
    n = agg.get("games_analyzed", 0)
    acc = agg.get("chesscom_avg_accuracy")
    acc_str = f" · avg accuracy {acc}%" if acc is not None else ""
    body = [
        f"<h1>Chess analysis ({n} games{acc_str})</h1>",
        section_charts(agg),
        section_blunder_origin(games),
        section_openings(agg, games, pgn_by_url),
        section_top_blunders(agg, pgn_by_url, games=games),
        section_study_plan(agg, tips_md),
        section_glossary(),
    ]
    return (
        '<!DOCTYPE html>\n<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>Chess analysis</title>\n"
        f"<style>{STYLE}</style>\n</head>\n<body>\n"
        + "\n".join(body)
        + "\n"
        + BOARD_SCRIPT
        + "\n</body>\n</html>\n"
    )


def load(in_dir: str) -> tuple[dict, list, list]:
    """Read aggregate.json, analysis.json, and games.json (PGNs) from in_dir."""
    d = Path(in_dir)
    agg_file = d / "aggregate.json"
    ana_file = d / "analysis.json"
    games_file = d / "games.json"
    if not agg_file.exists():
        raise SystemExit(f"{agg_file} not found — run analyze_games.py first.")
    agg = json.loads(agg_file.read_text())
    games = json.loads(ana_file.read_text()) if ana_file.exists() else []
    raw_games = (
        json.loads(games_file.read_text()).get("games", [])
        if games_file.exists()
        else []
    )
    return agg, games, raw_games


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--in", dest="in_dir", default=DEFAULT_DIR, help="dir with the analysis JSON"
    )
    ap.add_argument("--tips", default=None, help="Markdown file of coaching prose")
    args = ap.parse_args()

    agg, games, raw_games = load(args.in_dir)
    tips_md = Path(args.tips).read_text() if args.tips else None
    out = Path(args.in_dir) / "report.html"
    out.write_text(build_html(agg, games, raw_games, tips_md))
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
