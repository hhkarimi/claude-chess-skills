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
import json
from pathlib import Path

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
"""


def _esc(s: object) -> str:
    return html.escape(str(s))


def svg_bars(rows: list[tuple[str, float]], *, unit: str = "",
             color: str = "#3b6ea5", width: int = 720) -> str:
    """Horizontal bar chart as inline SVG. rows = [(label, value), ...].

    Rows with a None value are skipped; zero values render a label with no bar.
    """
    rows = [(lab, v) for lab, v in rows if v is not None]
    if not rows:
        return '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"></svg>'
    row_h, pad_l, pad_r, top = 28, 130, 70, 8
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
        parts.append(
            f'<text x="0" y="{cy + 4}" font-size="13">{_esc(label)}</text>'
        )
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
    return "\n".join([
        "<h2>Charts</h2>",
        _chart("Results by color", svg_bars(results_rows)),
        color_table,
        _chart("Average centipawn loss by phase (lower is better)",
               svg_bars(phase_rows, unit=" cpl", color="#a5563b")),
        _chart("Move quality", svg_bars(mq_rows, color="#7a3ba5")),
        _chart("Average centipawn loss — wins vs losses",
               svg_bars(res_rows, unit=" cpl", color="#3b8aa5")),
        "<h3>Time trouble</h3>",
        '<ul class="muted">'
        f"<li>Moves in time trouble: {tt.get('my_moves_in_time_trouble', 0)}</li>"
        f"<li>Blunders in time trouble: {tt.get('blunders_in_time_trouble', 0)} "
        f"({share_str} of all blunders)</li>"
        f"<li>Losses with a time-trouble blunder: "
        f"{tt.get('losses_with_time_trouble_blunder', 0)}</li></ul>",
    ])


def pov(color: str, cp: float) -> float:
    """White-POV centipawns -> the mover's POV (positive = good for mover)."""
    return cp if color == "white" else -cp


def blunder_origin_buckets(games: list) -> dict:
    """Count blunders by the player-POV eval *before* the blunder move."""
    out = {"winning": 0, "equal": 0, "losing": 0}
    for g in games:
        color = g.get("my_color", "white")
        for m in g.get("moves", []):
            if m.get("class") != "blunder":
                continue
            e = pov(color, m.get("eval_before", 0))
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
    return "\n".join([
        "<h2>Where your blunders come from</h2>",
        '<p class="muted">Each blunder bucketed by the engine eval (your point of '
        "view) on the move just before it. Blunders thrown from winning or equal "
        "positions are the ones you can most directly stop.</p>",
        _chart("Blunders by position strength before the mistake",
               svg_bars(rows, color="#b5482f")),
    ])


def eval_series(game: dict) -> list:
    """Player-POV eval after each of the player's moves, in order."""
    color = game.get("my_color", "white")
    return [pov(color, m.get("eval_after", 0)) for m in game.get("moves", [])]


def svg_sparkline(values: list, *, mark_index: int | None = None,
                  width: int = 320, height: int = 70) -> str:
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


def section_trajectories(agg: dict, games: list, limit: int = 6) -> str:
    by_url = {g.get("url"): g for g in games}
    seen, cards = set(), []
    for b in agg.get("top_blunders", []):
        url = b.get("game_url")
        if url in seen or url not in by_url:
            continue
        seen.add(url)
        g = by_url[url]
        series = eval_series(g)
        idx = next(
            (i for i, m in enumerate(g.get("moves", []))
             if m.get("move_no") == b.get("move_no")),
            None,
        )
        sep = ". " if b.get("color") == "white" else "..."
        move = f"{b.get('move_no')}{sep}{b.get('san')}"
        link = f'<a href="{_esc(url)}">replay</a>' if url else ""
        cards.append(
            '<div class="card">'
            f"<strong>{_esc(move)}</strong> "
            f'<span class="muted">(swing {_esc(b.get("raw_swing"))}cp)</span> {link}<br>'
            f"{svg_sparkline(series, mark_index=idx)}</div>"
        )
        if len(cards) >= limit:
            break
    if not cards:
        return ""
    return "\n".join([
        "<h2>Eval trajectory into your biggest blunders</h2>",
        '<p class="muted">Your evaluation across each game (your point of view), '
        "with the blunder marked. Look for whether the line was already sliding or "
        "fell off a cliff in one move.</p>",
        *cards,
    ])


def build_html(agg: dict, games: list, tips_md: str | None = None) -> str:
    """Assemble the full self-contained HTML document."""
    n = agg.get("games_analyzed", 0)
    acc = agg.get("chesscom_avg_accuracy")
    acc_str = f" · avg accuracy {acc}%" if acc is not None else ""
    body = [
        f"<h1>Chess analysis ({n} games{acc_str})</h1>",
        section_charts(agg),
        section_blunder_origin(games),
        section_trajectories(agg, games),
    ]
    return (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>Chess analysis</title>\n"
        f"<style>{STYLE}</style>\n</head>\n<body>\n"
        + "\n".join(body)
        + "\n</body>\n</html>\n"
    )


def load(in_dir: str) -> tuple[dict, list]:
    """Read aggregate.json (summary) and analysis.json (per-move) from in_dir."""
    d = Path(in_dir)
    agg_file = d / "aggregate.json"
    ana_file = d / "analysis.json"
    if not agg_file.exists():
        raise SystemExit(f"{agg_file} not found — run analyze_games.py first.")
    agg = json.loads(agg_file.read_text())
    games = json.loads(ana_file.read_text()) if ana_file.exists() else []
    return agg, games


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--in", dest="in_dir", default=DEFAULT_DIR, help="dir with the analysis JSON"
    )
    ap.add_argument("--tips", default=None, help="Markdown file of coaching prose")
    args = ap.parse_args()

    agg, games = load(args.in_dir)
    tips_md = Path(args.tips).read_text() if args.tips else None
    out = Path(args.in_dir) / "report.html"
    out.write_text(build_html(agg, games, tips_md))
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
