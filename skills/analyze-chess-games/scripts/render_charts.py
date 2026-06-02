# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Render aggregate.json as inline ASCII charts + tables for the report.

Stdlib only — emits Markdown where each chart is a fenced code block so the
monospace bar alignment survives being pasted into a terminal or chat. Claude
includes this output near the top of the report, then writes the prioritized
tips below it.

Usage:
    uv run render_charts.py [--in ./chess-analysis]
"""

import argparse
import json
import sys
from pathlib import Path

BAR_WIDTH = 28
FILL = "█"


def bar(value: float, max_value: float, width: int = BAR_WIDTH) -> str:
    """A horizontal bar of block characters, length proportional to value/max."""
    if max_value <= 0 or value <= 0:
        return ""
    filled = round(width * value / max_value)
    return FILL * max(1, min(width, filled))


def _fenced(title: str, body: str) -> str:
    """Wrap a chart body in a titled fenced code block (preserves alignment)."""
    return f"**{title}**\n\n```\n{body}\n```"


def render_value_bars(
    rows: list[tuple[str, float]], *, unit: str = "", value_fmt: str = "{:g}"
) -> str:
    """rows = [(label, value), ...] -> aligned label + bar + value lines."""
    rows = [(label, v) for label, v in rows if v is not None]
    if not rows:
        return "(no data)"
    max_v = max(v for _, v in rows) or 1
    label_w = max(len(label) for label, _ in rows)
    lines = []
    for label, v in rows:
        lines.append(
            f"{label:<{label_w}}  {bar(v, max_v):<{BAR_WIDTH}}  {value_fmt.format(v)}{unit}"
        )
    return "\n".join(lines)


def render_results_by_color(agg: dict) -> str:
    by_color = agg.get("by_color", {})
    lines = []
    header = f"{'':<6}  {'W':>3} {'L':>3} {'D':>3}  {'win%':>5}"
    lines.append(header)
    for color in ("white", "black"):
        rec = by_color.get(color, {})
        w, loss, d = rec.get("win", 0), rec.get("loss", 0), rec.get("draw", 0)
        total = w + loss + d
        wr = f"{100 * w / total:.0f}%" if total else "-"
        lines.append(f"{color.title():<6}  {w:>3} {loss:>3} {d:>3}  {wr:>5}")
    res = agg.get("results", {})
    w, loss, d = res.get("win", 0), res.get("loss", 0), res.get("draw", 0)
    total = w + loss + d or 1
    lines.append("")
    lines.append(render_value_bars([("Wins", w), ("Losses", loss), ("Draws", d)]))
    lines.append("")
    lines.append(f"Overall: {w}W / {loss}L / {d}D  ({100 * w / total:.0f}% win rate)")
    return "\n".join(lines)


def render_cpl_by_phase(agg: dict) -> str:
    phase = agg.get("avg_cpl_by_phase", {})
    rows = [(p.title(), phase.get(p)) for p in ("opening", "middlegame", "endgame")]
    return render_value_bars(rows, value_fmt="{:.0f}")


def render_move_quality(agg: dict) -> str:
    mq = agg.get("move_quality", {})
    rows = [
        ("Blunders", mq.get("blunders", 0)),
        ("Mistakes", mq.get("mistakes", 0)),
        ("Inaccuracies", mq.get("inaccuracies", 0)),
    ]
    body = render_value_bars(rows, value_fmt="{:.0f}")
    bpg = mq.get("blunders_per_game")
    mpg = mq.get("mistakes_per_game")
    if bpg is not None:
        body += f"\n\nPer game: {bpg} blunders, {mpg} mistakes"
    return body


def render_cpl_by_result(agg: dict) -> str:
    r = agg.get("avg_cpl_by_result", {})
    rows = [
        ("In wins", r.get("win")),
        ("In losses", r.get("loss")),
        ("In draws", r.get("draw")),
    ]
    return render_value_bars(rows, value_fmt="{:.0f}", unit=" cpl")


def render_mistakes_table(agg: dict) -> str:
    """Mistakes-by-phase as a Markdown table."""
    bbp = agg.get("blunders_by_phase", {})
    lines = [
        "| Phase | Blunders | Mistakes | Inaccuracies |",
        "|---|---:|---:|---:|",
    ]
    for p in ("opening", "middlegame", "endgame"):
        c = bbp.get(p, {})
        lines.append(
            f"| {p.title()} | {c.get('blunder', 0)} | {c.get('mistake', 0)} | {c.get('inaccuracy', 0)} |"
        )
    return "\n".join(lines)


def render_time_trouble(agg: dict) -> str:
    tt = agg.get("time_trouble", {})
    share = tt.get("share_of_blunders_in_time_trouble")
    share_str = f"{100 * share:.0f}%" if share is not None else "-"
    return (
        f"Moves played in time trouble : {tt.get('my_moves_in_time_trouble', 0)}\n"
        f"Blunders in time trouble     : {tt.get('blunders_in_time_trouble', 0)} "
        f"({share_str} of all blunders)\n"
        f"Losses with a TT blunder     : {tt.get('losses_with_time_trouble_blunder', 0)}"
    )


def render_openings(agg: dict, limit: int = 8) -> str:
    """Opening performance as a Markdown table."""
    ops = agg.get("opening_performance", [])
    if not ops:
        return "(no opening played 2+ times in this sample)"
    lines = [
        "| Opening | Color | Record | Win% | Opening CPL |",
        "|---|---|---|---:|---:|",
    ]
    for o in ops[:limit]:
        rec = f"{o['win']}-{o['loss']}-{o['draw']}"
        wr = f"{100 * o['win'] / o['games']:.0f}%"
        cpl = o.get("avg_opening_cpl")
        cpl_str = f"{cpl:.0f}" if cpl is not None else "-"
        lines.append(
            f"| {o['opening']} | {o['color'].title()} | {rec} | {wr} | {cpl_str} |"
        )
    return "\n".join(lines)


def render_top_blunders(agg: dict, limit: int = 8) -> str:
    """Top blunders as a Markdown table with chess.com game links."""
    blunders = agg.get("top_blunders", [])
    if not blunders:
        return "(no blunders found)"
    lines = [
        "| Eval swing | Move | Phase | Color | Result | Game |",
        "|---:|---|---|---|---|---|",
    ]
    for b in blunders[:limit]:
        # white moves render "12. Nf3", black moves "12...Nf6"
        sep = ". " if b["color"] == "white" else "..."
        move = f"{b['move_no']}{sep}{b['san']}"
        url = b.get("game_url") or ""
        game = f"[link]({url})" if url else "-"
        lines.append(
            f"| {b['raw_swing']} cp | {move} | {b['phase']} | "
            f"{b['color'].title()} | {b['result']} | {game} |"
        )
    return "\n".join(lines)


def build_report_charts(agg: dict) -> str:
    n = agg.get("games_analyzed", 0)
    acc = agg.get("chesscom_avg_accuracy")
    acc_str = f" · avg accuracy {acc}%" if acc is not None else ""
    sections = [
        f"## Game analysis ({n} games{acc_str})",
        "### Charts",
        _fenced("Results by color", render_results_by_color(agg)),
        _fenced(
            "Average centipawn loss by phase (lower is better)",
            render_cpl_by_phase(agg),
        ),
        _fenced("Move quality (last %d games)" % n, render_move_quality(agg)),
        _fenced("Average centipawn loss — wins vs losses", render_cpl_by_result(agg)),
        _fenced("Time trouble", render_time_trouble(agg)),
        "### Tables",
        "**Mistakes by phase**\n\n" + render_mistakes_table(agg),
        "**Opening performance (2+ games)**\n\n" + render_openings(agg),
        "**Top blunders (biggest eval swings)**\n\n" + render_top_blunders(agg),
    ]
    return "\n\n".join(sections)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--in",
        dest="in_dir",
        default="chess-analysis",
        help="dir with aggregate-<username>.json (e.g. chess-analysis/<username>)",
    )
    args = ap.parse_args()

    d = Path(args.in_dir)
    matches = sorted(d.glob("aggregate*.json"))
    if not matches:
        raise SystemExit(f"No aggregate*.json in {d} — run analyze_games.py first.")
    if len(matches) > 1:
        names = ", ".join(p.name for p in matches)
        raise SystemExit(
            f"Multiple aggregate files in {d} ({names}); point --in at one "
            "user's directory."
        )

    agg = json.loads(matches[0].read_text())
    print(build_report_charts(agg))
    print(file=sys.stderr)
    print("Charts rendered. Paste the block above into the report.", file=sys.stderr)


if __name__ == "__main__":
    main()
