# HTML Report + cwd Output Path Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a self-contained `report.html` to the `analyze-chess-games` skill and move the default output directory from `/tmp/chess` to `./chess-analysis`.

**Architecture:** A new standalone PEP 723 script `render_report.py` (only dep: `python-chess`, used for `chess.svg` board diagrams) reads `aggregate.json` + `analysis.json` and emits one self-contained HTML file with inline CSS, hand-rolled inline SVG charts, opening/blunder board diagrams, and a study plan. `render_charts.py` stays untouched and stdlib-only. The default path change is a coordinated edit across the four scripts plus docs and `.gitignore`.

**Tech Stack:** Python 3.11+, `uv` (PEP 723 inline deps), `python-chess` (`chess.svg`), pytest. Scripts are standalone (not a package); tests import them by module name via `tests/conftest.py`, which puts the scripts dir on `sys.path`.

**Conventions:** Conventional Commits (`feat:` for user-visible features, `chore:`/`docs:` otherwise). Run `uvx ruff check .` and `uvx ruff format .` before committing. Run tests with `uv run --with chess --with pytest pytest tests -v`.

---

## File Structure

- Create: `skills/analyze-chess-games/scripts/render_report.py` — the HTML report generator. One responsibility: turn the analysis JSON into a self-contained HTML file. Pure functions per section plus a `main()`.
- Create: `tests/test_report.py` — unit tests for `render_report`, built from inline dicts (matching the style of `tests/test_charts.py` / `tests/test_analyze.py`; no fixture files).
- Modify: `skills/analyze-chess-games/scripts/fetch_games.py` — default `--out` and docstring.
- Modify: `skills/analyze-chess-games/scripts/analyze_games.py` — default `--in` and docstring.
- Modify: `skills/analyze-chess-games/scripts/render_charts.py` — default `--in` and docstring.
- Modify: `.gitignore` — ignore `chess-analysis/`.
- Modify: `skills/analyze-chess-games/SKILL.md` — new render step, new default paths.
- Modify: `CLAUDE.md` — architecture note, local commands, default paths.

---

## Task 1: Move default output dir to `./chess-analysis`

**Files:**
- Modify: `skills/analyze-chess-games/scripts/fetch_games.py:13` and `:147`
- Modify: `skills/analyze-chess-games/scripts/analyze_games.py:28` and `:358`
- Modify: `skills/analyze-chess-games/scripts/render_charts.py:13` and `:202`
- Modify: `.gitignore`

- [ ] **Step 1: Change the fetcher default**

In `skills/analyze-chess-games/scripts/fetch_games.py`, change the docstring usage line (currently `:13`):

```
    uv run fetch_games.py <username> [--count 100] [--out ./chess-analysis]
```

and the argparse default (currently `:147`):

```python
        "--out", default="chess-analysis", help="output directory (default ./chess-analysis)"
```

- [ ] **Step 2: Change the analyzer default**

In `skills/analyze-chess-games/scripts/analyze_games.py`, change the docstring usage line (currently `:28`):

```
    uv run analyze_games.py [--in ./chess-analysis] [--depth 12] [--max-games N]
```

and the argparse default (currently `:358`):

```python
        "--in", dest="in_dir", default="chess-analysis", help="dir with games.json"
```

- [ ] **Step 3: Change the chart renderer default**

In `skills/analyze-chess-games/scripts/render_charts.py`, change the docstring usage line (currently `:13`):

```
    uv run render_charts.py [--in ./chess-analysis]
```

and the argparse default (currently `:202`):

```python
        "--in", dest="in_dir", default="chess-analysis", help="dir with aggregate.json"
```

- [ ] **Step 4: Ignore the output directory**

In `.gitignore`, add `chess-analysis/` immediately after the `/tmp/` line so the per-run artifacts (including `report.html`, which carries the username and game data) are never committed:

```
/tmp/
chess-analysis/
```

- [ ] **Step 5: Verify the defaults changed**

Run:
```bash
cd skills/analyze-chess-games/scripts
uv run fetch_games.py --help 2>&1 | grep chess-analysis
uv run analyze_games.py --help 2>&1 | grep chess-analysis
uv run render_charts.py --help 2>&1 | grep chess-analysis
```
Expected: each prints a line containing `./chess-analysis` / `chess-analysis`.

- [ ] **Step 6: Confirm no stale `/tmp/chess` in scripts**

Run: `grep -rn "/tmp/chess" skills/analyze-chess-games/scripts/`
Expected: no output (docs are handled in Task 9).

- [ ] **Step 7: Commit**

```bash
cd ../../..
git add skills/analyze-chess-games/scripts/fetch_games.py skills/analyze-chess-games/scripts/analyze_games.py skills/analyze-chess-games/scripts/render_charts.py .gitignore
git commit -m "feat: default output dir to ./chess-analysis (was /tmp/chess)"
```

---

## Task 2: `render_report.py` skeleton — load inputs and build an HTML shell

**Files:**
- Create: `skills/analyze-chess-games/scripts/render_report.py`
- Test: `tests/test_report.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_report.py`:

```python
"""Unit tests for render_report HTML generation (no engine run, no network)."""

import render_report as rr


def _min_agg():
    return {
        "games_analyzed": 2,
        "chesscom_avg_accuracy": 70.0,
        "by_color": {"white": {"win": 1, "loss": 1, "draw": 0}},
        "results": {"win": 1, "loss": 1, "draw": 0},
        "avg_cpl_by_phase": {"opening": 30, "middlegame": 90, "endgame": 80},
        "move_quality": {
            "blunders": 4, "mistakes": 6, "inaccuracies": 8,
            "blunders_per_game": 2.0, "mistakes_per_game": 3.0,
        },
        "avg_cpl_by_result": {"win": 50, "loss": 95, "draw": 20},
        "blunders_by_phase": {"middlegame": {"blunder": 4, "mistake": 6, "inaccuracy": 8}},
        "time_trouble": {
            "my_moves_in_time_trouble": 5, "blunders_in_time_trouble": 1,
            "losses_with_time_trouble_blunder": 1,
            "share_of_blunders_in_time_trouble": 0.25,
        },
        "opening_performance": [],
        "top_blunders": [],
    }


def test_build_html_is_a_full_document():
    html = rr.build_html(_min_agg(), [])
    assert html.lstrip().startswith("<!DOCTYPE html>")
    assert "<html" in html and "</html>" in html
    assert "<style>" in html  # self-contained, inline CSS
    assert "2 games" in html  # summary header rendered
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --with chess --with pytest pytest tests/test_report.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'render_report'`.

- [ ] **Step 3: Write the minimal implementation**

Create `skills/analyze-chess-games/scripts/render_report.py`:

```python
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


def build_html(agg: dict, games: list, tips_md: str | None = None) -> str:
    """Assemble the full self-contained HTML document."""
    n = agg.get("games_analyzed", 0)
    acc = agg.get("chesscom_avg_accuracy")
    acc_str = f" · avg accuracy {acc}%" if acc is not None else ""
    body = [f"<h1>Chess analysis ({n} games{acc_str})</h1>"]
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --with chess --with pytest pytest tests/test_report.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add skills/analyze-chess-games/scripts/render_report.py tests/test_report.py
git commit -m "feat: add render_report.py HTML shell"
```

---

## Task 3: Inline SVG bar charts for the aggregate metrics

**Files:**
- Modify: `skills/analyze-chess-games/scripts/render_report.py`
- Test: `tests/test_report.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_report.py`:

```python
def test_svg_bars_emits_one_rect_per_nonzero_row():
    svg = rr.svg_bars([("Opening", 30), ("Middlegame", 90), ("Endgame", 0)])
    assert svg.startswith("<svg")
    assert svg.count("<rect") == 2  # zero-valued row drawn as label only
    assert "Middlegame" in svg
    assert "90" in svg


def test_section_charts_has_all_metric_headings():
    out = rr.section_charts(_min_agg())
    for heading in ("Results by color", "centipawn loss by phase",
                    "Move quality", "wins vs losses", "Time trouble"):
        assert heading in out
    assert "<svg" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --with chess --with pytest pytest tests/test_report.py -k "svg_bars or section_charts" -v`
Expected: FAIL with `AttributeError: module 'render_report' has no attribute 'svg_bars'`.

- [ ] **Step 3: Write the implementation**

In `render_report.py`, add after `STYLE` (before `build_html`):

```python
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
```

Then update `build_html` to include the section. Replace the `body = [...]` line with:

```python
    body = [
        f"<h1>Chess analysis ({n} games{acc_str})</h1>",
        section_charts(agg),
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --with chess --with pytest pytest tests/test_report.py -v`
Expected: PASS (all tests, including Task 2's).

- [ ] **Step 5: Commit**

```bash
git add skills/analyze-chess-games/scripts/render_report.py tests/test_report.py
git commit -m "feat: render aggregate metrics as inline SVG bar charts"
```

---

## Task 4: Blunder-origin chart (where blunders come from)

**Files:**
- Modify: `skills/analyze-chess-games/scripts/render_report.py`
- Test: `tests/test_report.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_report.py`:

```python
def _games_with_blunders():
    # white blundering from a winning (+500) and an equal (+20) position;
    # black blundering from a losing (white +400 => black -400) position.
    return [
        {"my_color": "white", "url": "https://chess.com/g/1", "moves": [
            {"class": "blunder", "eval_before": 500},
            {"class": None, "eval_before": -100},
            {"class": "blunder", "eval_before": 20},
        ]},
        {"my_color": "black", "url": "https://chess.com/g/2", "moves": [
            {"class": "blunder", "eval_before": 400},
        ]},
    ]


def test_blunder_origin_buckets_use_player_pov_and_sum_to_total():
    buckets = rr.blunder_origin_buckets(_games_with_blunders())
    assert buckets == {"winning": 1, "equal": 1, "losing": 1}
    assert sum(buckets.values()) == 3


def test_section_blunder_origin_renders_chart():
    out = rr.section_blunder_origin(_games_with_blunders())
    assert "Where your blunders come from" in out
    assert "<svg" in out
    assert "winning" in out.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --with chess --with pytest pytest tests/test_report.py -k "blunder_origin" -v`
Expected: FAIL with `AttributeError: module 'render_report' has no attribute 'blunder_origin_buckets'`.

- [ ] **Step 3: Write the implementation**

In `render_report.py`, add after `section_charts`:

```python
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
```

Update `build_html` body to insert the section after charts:

```python
    body = [
        f"<h1>Chess analysis ({n} games{acc_str})</h1>",
        section_charts(agg),
        section_blunder_origin(games),
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --with chess --with pytest pytest tests/test_report.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add skills/analyze-chess-games/scripts/render_report.py tests/test_report.py
git commit -m "feat: add blunder-origin chart by pre-blunder eval"
```

---

## Task 5: Eval-trajectory sparklines for top-blunder games

**Files:**
- Modify: `skills/analyze-chess-games/scripts/render_report.py`
- Test: `tests/test_report.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_report.py`:

```python
def test_eval_series_is_player_pov():
    game = {"my_color": "black", "moves": [
        {"eval_after": 100}, {"eval_after": -200},
    ]}
    assert rr.eval_series(game) == [-100, 200]


def test_svg_sparkline_marks_the_blunder_index():
    svg = rr.svg_sparkline([100, 50, -300, -280], mark_index=2)
    assert svg.startswith("<svg")
    assert "<polyline" in svg
    assert "<circle" in svg  # the marked blunder point


def test_section_trajectories_one_chart_per_blunder_game():
    agg = {"top_blunders": [
        {"game_url": "https://chess.com/g/1", "move_no": 2, "san": "Qxf7",
         "color": "white", "raw_swing": 2000},
    ]}
    games = [{"url": "https://chess.com/g/1", "my_color": "white", "moves": [
        {"move_no": 1, "eval_after": 500}, {"move_no": 2, "eval_after": -1500},
    ]}]
    out = rr.section_trajectories(agg, games)
    assert "Eval trajectory" in out
    assert out.count("<svg") >= 1
    assert "Qxf7" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --with chess --with pytest pytest tests/test_report.py -k "eval_series or sparkline or trajectories" -v`
Expected: FAIL with `AttributeError: module 'render_report' has no attribute 'eval_series'`.

- [ ] **Step 3: Write the implementation**

In `render_report.py`, add after `section_blunder_origin`:

```python
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
```

Update `build_html` body to append the section after blunder-origin:

```python
    body = [
        f"<h1>Chess analysis ({n} games{acc_str})</h1>",
        section_charts(agg),
        section_blunder_origin(games),
        section_trajectories(agg, games),
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --with chess --with pytest pytest tests/test_report.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add skills/analyze-chess-games/scripts/render_report.py tests/test_report.py
git commit -m "feat: add eval-trajectory sparklines for top blunders"
```

---

## Task 6: Opening figures (board diagram per opening)

**Files:**
- Modify: `skills/analyze-chess-games/scripts/render_report.py`
- Test: `tests/test_report.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_report.py`:

```python
def test_opening_position_fen_stops_at_end_of_opening():
    game = {"moves": [
        {"phase": "opening", "fen_before": "FEN_OPENING_1"},
        {"phase": "opening", "fen_before": "FEN_OPENING_2"},
        {"phase": "middlegame", "fen_before": "FEN_MIDDLE"},
    ]}
    assert rr.opening_position_fen(game) == "FEN_MIDDLE"


def test_opening_position_fen_all_opening_uses_last():
    game = {"moves": [
        {"phase": "opening", "fen_before": "A"},
        {"phase": "opening", "fen_before": "B"},
    ]}
    assert rr.opening_position_fen(game) == "B"


def test_board_svg_renders_real_svg_from_startpos():
    import chess
    svg = rr.board_svg(chess.STARTING_FEN, color="white")
    assert "<svg" in svg


def test_section_openings_includes_board_when_game_matches():
    agg = {"opening_performance": [
        {"opening": "Scotch Game", "color": "white", "games": 2,
         "win": 2, "loss": 0, "draw": 0, "avg_opening_cpl": 40.0},
    ]}
    import chess
    games = [{"opening": "Scotch Game", "my_color": "white", "moves": [
        {"phase": "opening", "fen_before": chess.STARTING_FEN},
        {"phase": "middlegame", "fen_before": chess.STARTING_FEN},
    ]}]
    out = rr.section_openings(agg, games)
    assert "Scotch Game" in out
    assert "<svg" in out  # board rendered
    assert "2-0-0" in out


def test_section_openings_empty_is_graceful():
    out = rr.section_openings({"opening_performance": []}, [])
    assert "no opening" in out.lower()
    assert "<svg" not in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --with chess --with pytest pytest tests/test_report.py -k "opening or board_svg" -v`
Expected: FAIL with `AttributeError: module 'render_report' has no attribute 'opening_position_fen'`.

- [ ] **Step 3: Write the implementation**

At the top of `render_report.py`, add the chess imports under the existing imports:

```python
import chess
import chess.svg
```

Then add after `section_trajectories`:

```python
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


def _find_opening_game(games: list, opening: str, color: str) -> dict | None:
    for g in games:
        if g.get("opening") == opening and g.get("my_color") == color:
            return g
    return None


def section_openings(agg: dict, games: list, limit: int = 8) -> str:
    ops = agg.get("opening_performance", [])
    if not ops:
        return ("<h2>Openings</h2>"
                "<p class='muted'>(no opening played 2+ times in this sample)</p>")
    cards = []
    for o in ops[:limit]:
        rec = f"{o['win']}-{o['loss']}-{o['draw']}"
        wr = f"{100 * o['win'] / o['games']:.0f}%" if o.get("games") else "-"
        cpl = o.get("avg_opening_cpl")
        cpl_str = f"{cpl:.0f}" if cpl is not None else "-"
        g = _find_opening_game(games, o["opening"], o["color"])
        fen = opening_position_fen(g) if g else None
        board = (
            f'<div class="board">{board_svg(fen, color=o["color"])}</div>'
            if fen else ""
        )
        cards.append(
            '<div class="card">'
            f"<h3>{_esc(o['opening'])} <span class='muted'>"
            f"({_esc(o['color'].title())})</span></h3>"
            f"{board}"
            "<div>"
            f"<p>Record: <strong>{_esc(rec)}</strong> · Win rate: {_esc(wr)} · "
            f"Opening CPL: {_esc(cpl_str)}</p></div></div>"
        )
    return "<h2>Openings</h2>\n" + "\n".join(cards)
```

Update `build_html` body to append after trajectories:

```python
    body = [
        f"<h1>Chess analysis ({n} games{acc_str})</h1>",
        section_charts(agg),
        section_blunder_origin(games),
        section_trajectories(agg, games),
        section_openings(agg, games),
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --with chess --with pytest pytest tests/test_report.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add skills/analyze-chess-games/scripts/render_report.py tests/test_report.py
git commit -m "feat: add per-opening board diagrams"
```

---

## Task 7: Top-blunders drill section (board from fen_before)

**Files:**
- Modify: `skills/analyze-chess-games/scripts/render_report.py`
- Test: `tests/test_report.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_report.py`:

```python
def test_section_top_blunders_renders_boards_and_links():
    import chess
    agg = {"top_blunders": [
        {"game_url": "https://chess.com/g/1", "move_no": 20, "san": "Qxf7",
         "phase": "middlegame", "color": "white", "result": "loss",
         "raw_swing": 2540, "fen_before": chess.STARTING_FEN},
    ]}
    out = rr.section_top_blunders(agg)
    assert "Top blunders" in out
    assert "<svg" in out  # board from fen_before
    assert "20. Qxf7" in out
    assert "https://chess.com/g/1" in out
    assert "2540" in out


def test_section_top_blunders_empty_is_graceful():
    out = rr.section_top_blunders({"top_blunders": []})
    assert "no blunders" in out.lower()
    assert "<svg" not in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --with chess --with pytest pytest tests/test_report.py -k "top_blunders" -v`
Expected: FAIL with `AttributeError: module 'render_report' has no attribute 'section_top_blunders'`.

- [ ] **Step 3: Write the implementation**

In `render_report.py`, add after `section_openings`:

```python
def section_top_blunders(agg: dict, limit: int = 8) -> str:
    blunders = agg.get("top_blunders", [])
    if not blunders:
        return "<h2>Top blunders</h2><p class='muted'>(no blunders found)</p>"
    cards = []
    for b in blunders[:limit]:
        sep = ". " if b.get("color") == "white" else "..."
        move = f"{b.get('move_no')}{sep}{b.get('san')}"
        fen = b.get("fen_before")
        board = (
            f'<div class="board">{board_svg(fen, color=b.get("color", "white"))}</div>'
            if fen else ""
        )
        url = b.get("game_url") or ""
        link = f'<a href="{_esc(url)}">replay on chess.com</a>' if url else ""
        cards.append(
            '<div class="card">'
            f"<h3>{_esc(move)} "
            f"<span class='muted'>· swing {_esc(b.get('raw_swing'))}cp</span></h3>"
            f"{board}"
            "<div>"
            f"<p>{_esc(b.get('phase'))} · {_esc(b.get('color'))} · "
            f"{_esc(b.get('result'))}</p>"
            f"<p>{link}</p></div></div>"
        )
    return "\n".join([
        "<h2>Top blunders</h2>",
        '<p class="muted">The position is shown just before the move you played. '
        "Try to find the move you should have made before clicking through.</p>",
        *cards,
    ])
```

Update `build_html` body to append after openings:

```python
    body = [
        f"<h1>Chess analysis ({n} games{acc_str})</h1>",
        section_charts(agg),
        section_blunder_origin(games),
        section_trajectories(agg, games),
        section_openings(agg, games),
        section_top_blunders(agg),
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --with chess --with pytest pytest tests/test_report.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add skills/analyze-chess-games/scripts/render_report.py tests/test_report.py
git commit -m "feat: add top-blunder drill boards"
```

---

## Task 8: Study plan section (data scaffold + optional Claude prose)

**Files:**
- Modify: `skills/analyze-chess-games/scripts/render_report.py`
- Test: `tests/test_report.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_report.py`:

```python
def test_md_to_html_handles_headings_bullets_and_paragraphs():
    out = rr.md_to_html("## Focus\n\nWork on tactics.\n\n- one\n- two")
    assert "<h3>Focus</h3>" in out
    assert "<p>Work on tactics.</p>" in out
    assert "<li>one</li>" in out and "<li>two</li>" in out
    assert "<ul>" in out


def test_md_to_html_escapes_html():
    assert "&lt;script&gt;" in rr.md_to_html("<script>")


def test_section_study_plan_ranks_phase_and_lists_drills():
    agg = {
        "avg_cpl_by_phase": {"opening": 30, "middlegame": 95, "endgame": 80},
        "blunders_by_phase": {
            "opening": {"blunder": 2}, "middlegame": {"blunder": 10},
            "endgame": {"blunder": 7},
        },
        "opening_performance": [
            {"opening": "Italian Game", "color": "black", "games": 3,
             "win": 1, "loss": 2, "draw": 0, "avg_opening_cpl": 78.0},
            {"opening": "Scotch Game", "color": "white", "games": 5,
             "win": 5, "loss": 0, "draw": 0, "avg_opening_cpl": 39.0},
        ],
        "top_blunders": [
            {"game_url": "https://chess.com/g/1", "move_no": 20, "san": "Qxf7",
             "color": "white"},
        ],
    }
    out = rr.section_study_plan(agg)
    assert "Study plan" in out
    # middlegame has the worst CPL+blunders, so it should be the top priority
    assert out.index("Middlegame") < out.index("Endgame")
    # weak opening (losing record / high CPL) is flagged, strong one is not
    assert "Italian Game" in out
    assert "Scotch Game" not in out
    # a concrete drill link is included
    assert "https://chess.com/g/1" in out


def test_section_study_plan_injects_coach_notes_when_tips_given():
    out = rr.section_study_plan({"avg_cpl_by_phase": {}}, tips_md="## Hi\n\nFocus here.")
    assert "Coach's notes" in out
    assert "Focus here." in out


def test_section_study_plan_no_coach_notes_without_tips():
    out = rr.section_study_plan({"avg_cpl_by_phase": {}})
    assert "Coach's notes" not in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --with chess --with pytest pytest tests/test_report.py -k "md_to_html or study_plan" -v`
Expected: FAIL with `AttributeError: module 'render_report' has no attribute 'md_to_html'`.

- [ ] **Step 3: Write the implementation**

In `render_report.py`, add after `section_top_blunders`:

```python
def md_to_html(text: str) -> str:
    """Minimal Markdown -> HTML: #/##/### headings, '- ' bullets, blank-line
    paragraphs, and **bold**. Everything is HTML-escaped first."""
    import re

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

    for raw in lines:
        line = raw.rstrip()
        if not line.strip():
            flush_bullets()
            flush_para()
        elif line.startswith("### "):
            flush_bullets(); flush_para(); blocks.append(f"<h4>{inline(line[4:])}</h4>")
        elif line.startswith("## "):
            flush_bullets(); flush_para(); blocks.append(f"<h3>{inline(line[3:])}</h3>")
        elif line.startswith("# "):
            flush_bullets(); flush_para(); blocks.append(f"<h3>{inline(line[2:])}</h3>")
        elif line.lstrip().startswith("- "):
            flush_para(); bullets.append(inline(line.lstrip()[2:]))
        else:
            para.append(line)
    flush_bullets()
    flush_para()
    return "\n".join(blocks)


def section_study_plan(agg: dict, tips_md: str | None = None) -> str:
    parts = ["<h2>Study plan</h2>"]
    if tips_md:
        parts.append(
            '<div class="card coach"><h3>Coach\'s notes</h3>'
            + md_to_html(tips_md) + "</div>"
        )

    # 1. Rank phases by (avg CPL + blunder count) — biggest leak first.
    cpl = agg.get("avg_cpl_by_phase", {})
    bbp = agg.get("blunders_by_phase", {})
    phases = []
    for p in ("opening", "middlegame", "endgame"):
        score = (cpl.get(p) or 0) + (bbp.get(p, {}).get("blunder", 0) * 10)
        phases.append((p, score, cpl.get(p), bbp.get(p, {}).get("blunder", 0)))
    phases.sort(key=lambda t: t[1], reverse=True)
    phase_items = "".join(
        f"<li><strong>{p.title()}</strong>: "
        f"avg CPL {('-' if c is None else round(c))}, {bl} blunders</li>"
        for p, _, c, bl in phases
    )
    parts.append(
        "<h3>Phase priorities (worst leak first)</h3><ol>" + phase_items + "</ol>"
    )

    # 2. Weak openings: losing record or opening CPL > 60.
    weak = [
        o for o in agg.get("opening_performance", [])
        if o.get("loss", 0) > o.get("win", 0) or (o.get("avg_opening_cpl") or 0) > 60
    ]
    if weak:
        wk = "".join(
            f"<li>{_esc(o['opening'])} ({_esc(o['color'])}): "
            f"{o['win']}-{o['loss']}-{o['draw']}, "
            f"opening CPL {('-' if o.get('avg_opening_cpl') is None else round(o['avg_opening_cpl']))}</li>"
            for o in weak
        )
        parts.append("<h3>Openings to shore up</h3><ul>" + wk + "</ul>")

    # 3. Concrete drills from the top blunders.
    drills = agg.get("top_blunders", [])[:5]
    if drills:
        dl = "".join(
            f'<li><a href="{_esc(b.get("game_url", ""))}">'
            f"{b.get('move_no')}{'. ' if b.get('color') == 'white' else '...'}"
            f"{_esc(b.get('san'))}</a></li>"
            for b in drills
        )
        parts.append(
            "<h3>Replay these positions</h3>"
            '<p class="muted">Set each up and find the move you missed.</p>'
            "<ul>" + dl + "</ul>"
        )
    return "\n".join(parts)
```

Update `build_html` to accept and pass tips, and append the study plan last. Replace the whole `body = [...]` assignment with:

```python
    body = [
        f"<h1>Chess analysis ({n} games{acc_str})</h1>",
        section_charts(agg),
        section_blunder_origin(games),
        section_trajectories(agg, games),
        section_openings(agg, games),
        section_top_blunders(agg),
        section_study_plan(agg, tips_md),
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --with chess --with pytest pytest tests/test_report.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add skills/analyze-chess-games/scripts/render_report.py tests/test_report.py
git commit -m "feat: add data-driven study plan with optional coach notes"
```

---

## Task 9: End-to-end check, lint, and docs

**Files:**
- Test: `tests/test_report.py`
- Modify: `skills/analyze-chess-games/SKILL.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Write the failing integration test**

Append to `tests/test_report.py`:

```python
def test_build_html_full_document_has_every_section():
    agg = _min_agg()
    agg["opening_performance"] = [
        {"opening": "Scotch Game", "color": "white", "games": 2,
         "win": 2, "loss": 0, "draw": 0, "avg_opening_cpl": 40.0},
    ]
    agg["top_blunders"] = [
        {"game_url": "https://chess.com/g/1", "move_no": 20, "san": "Qxf7",
         "phase": "middlegame", "color": "white", "result": "loss",
         "raw_swing": 2540, "fen_before": __import__("chess").STARTING_FEN},
    ]
    games = [{"url": "https://chess.com/g/1", "my_color": "white",
              "opening": "Scotch Game", "moves": [
                  {"move_no": 1, "phase": "opening", "eval_before": 30,
                   "eval_after": 20, "class": None,
                   "fen_before": __import__("chess").STARTING_FEN},
                  {"move_no": 20, "phase": "middlegame", "eval_before": 541,
                   "eval_after": -1999, "class": "blunder",
                   "fen_before": __import__("chess").STARTING_FEN},
              ]}]
    html_out = rr.build_html(agg, games, tips_md="## Notes\n\nWatch your queen.")
    for heading in ("Charts", "Where your blunders come from",
                    "Eval trajectory", "Openings", "Top blunders", "Study plan",
                    "Coach's notes"):
        assert heading in html_out, heading
    assert html_out.strip().endswith("</html>")
```

- [ ] **Step 2: Run the full test file**

Run: `uv run --with chess --with pytest pytest tests/test_report.py -v`
Expected: PASS (all tests).

- [ ] **Step 3: Lint and format**

Run:
```bash
uvx ruff check skills/analyze-chess-games/scripts/render_report.py tests/test_report.py
uvx ruff format skills/analyze-chess-games/scripts/render_report.py tests/test_report.py
```
Expected: checks pass; formatter reports files unchanged or formats them. If it reformats, re-run the test from Step 2 to confirm still green.

- [ ] **Step 4: Run the whole suite and skill validation**

Run:
```bash
uv run --with chess --with pytest pytest tests -v
python3 tests/validate_skills.py
```
Expected: all tests pass; `OK: 1 SKILL.md files valid.`

- [ ] **Step 5: Real end-to-end smoke test**

Run (uses already-fetched data if present, else a tiny fetch):
```bash
cd skills/analyze-chess-games/scripts
uv run render_report.py --in /tmp/chess 2>&1 || true   # if old /tmp data exists
uv run render_report.py --help | grep -E "tips|chess-analysis"
cd ../../..
```
Expected: `--help` shows `--tips` and the `chess-analysis` default. If `/tmp/chess/aggregate.json` exists from earlier runs, a `report.html` is written there; open it to eyeball the charts and boards.

- [ ] **Step 6: Update SKILL.md**

In `skills/analyze-chess-games/SKILL.md`:

Add a render-report step after the existing "4. Render the charts" section (renumber the report step to 6 and shift "Write the report" if needed). Insert:

````markdown
### 5. Render the HTML report (optional, richer)

Generate a self-contained HTML report with SVG charts, per-opening board
diagrams, blunder-origin and eval-trajectory visualizations, and a study plan:

```bash
uv run scripts/render_report.py [--in ./chess-analysis] [--tips tips.md]
```

Writes `report.html` to the input dir — one file, no external assets, opens in
any browser offline. The study plan is generated from the data; if you pass
`--tips path/to/tips.md` (Markdown), your written coaching is injected as a
"Coach's notes" block at the top of the plan. Only the `python-chess` dependency
is needed (already used by the analyzer), and `render_charts.py` is unaffected.
````

SKILL.md still has the old `/tmp/chess` defaults (Task 1 only edited the scripts and `.gitignore`). Run `grep -n "/tmp/chess" skills/analyze-chess-games/SKILL.md` and replace every hit with `./chess-analysis` (lines for the fetch, analyze, and render-charts commands plus the "Default output dir is" prose near the top).

- [ ] **Step 7: Update CLAUDE.md**

In `CLAUDE.md`:

- Under "Architecture", add a bullet describing `render_report.py`: a separate PEP 723 script (dep: `python-chess` for `chess.svg`) that turns the analysis JSON into a self-contained `report.html`; note that `render_charts.py` stays stdlib-only.
- Under "Local commands", add:

```bash
uv run render_report.py --in ./chess-analysis   # self-contained HTML report
```

- Replace any remaining `/tmp/chess` and `--count 50` examples with `./chess-analysis` / `--count 100` if present. Run `grep -n "/tmp/chess" CLAUDE.md` and fix any hits.

- [ ] **Step 8: Commit docs**

```bash
git add skills/analyze-chess-games/SKILL.md CLAUDE.md tests/test_report.py
git commit -m "docs: document render_report.py and finalize chess-analysis paths"
```

---

## Done criteria

- `tests/test_report.py` passes under `uv run --with chess --with pytest pytest tests -v`.
- `uvx ruff check .` and `uvx ruff format --check .` pass.
- `python3 tests/validate_skills.py` reports the skill valid.
- `grep -rn "/tmp/chess" skills/ CLAUDE.md` returns nothing.
- `render_report.py --in <dir>` writes a single self-contained `report.html` containing all sections, with `--tips` injecting Coach's notes.

## PR

Branch `feat/html-report` off `main`. Open a PR titled
`feat: add self-contained HTML report with visualizations and study plan`.
Squash-merge (Conventional Commit title drives the release-please minor bump).
