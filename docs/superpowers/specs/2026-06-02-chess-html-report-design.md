# Design: self-contained HTML report with visualizations and study plan

Date: 2026-06-02
Skill: `analyze-chess-games`
Status: approved (pending spec review)

## Summary

Add a self-contained HTML report to the `analyze-chess-games` pipeline and move
the default output location out of `/tmp/chess` into a `./chess-analysis/` folder
under the current working directory. The HTML report renders the existing
dashboard metrics as real charts, adds two new "where do my blunders come from"
visualizations, draws a board diagram for each opening, turns each top blunder
into a replayable drill, and embeds a study plan built from the player's data
(with an optional slot for Claude-authored coaching prose).

This does not change the analysis math. It is a new presentation layer plus an
output-path change.

## Motivation

The current payoff lives in a Markdown/ASCII dashboard and chat-authored tips.
Two gaps:

1. The output sits in `/tmp/chess`, which is ephemeral and not next to the user's
   work. Users want the artifacts to persist where they run the skill.
2. Players ask "where do my blunders come from?" The ASCII dashboard shows phase
   CPL and a top-blunders table but does not visualize the *origin* of blunders
   (thrown from winning vs equal vs losing positions) or the eval trajectory into
   each blunder. A richer HTML report makes the pattern legible.

## Output path change

- Default `--out` (`fetch_games.py`) and `--in` (`analyze_games.py`,
  `render_charts.py`, `render_report.py`) change from `/tmp/chess` to
  `./chess-analysis` (relative to the current working directory).
- `--out` / `--in` continue to override the default.
- `.gitignore` gains `chess-analysis/` so the per-run artifacts (games.json,
  analysis.json, aggregate.json, report.html) — all of which carry the username
  and game data — are never committed. This upholds the existing CLAUDE.md rule:
  never commit usernames or game data.
- SKILL.md and CLAUDE.md command examples and prose updated to the new default.

### Data-safety note

The existing `.gitignore` excludes `games*.json`, `analysis*.json`,
`aggregate*.json`, `*.pgn`, and `/tmp/`, but not `*.html`. Moving output into the
repo/cwd would otherwise leave `report.html` (which contains game data)
unprotected. Ignoring the whole `chess-analysis/` directory closes this gap
regardless of file type.

## New component: `render_report.py`

- Location: `skills/analyze-chess-games/scripts/render_report.py`.
- PEP 723 inline deps: `dependencies = ["chess>=1.11"]`. `python-chess` is used
  only for `chess.svg` board rendering. It is already the analyzer's dependency,
  so no new package enters the project.
- Inputs: reads `aggregate.json` and `analysis.json` from `--in`
  (default `./chess-analysis`).
- Output: writes a single self-contained `report.html` to the same directory.
- Self-contained: inline CSS and inline SVG only. No CDN, no external JS
  charting library, no network access. Works offline and when opened from disk.
- Charts are hand-rolled inline SVG (bars and polylines built as strings), so the
  only dependency remains `python-chess`.

### Invariant preserved

`render_charts.py` stays untouched and stdlib-only. It keeps producing the
ASCII/Markdown dashboard for the chat. The HTML report is a separate, additive
script. The two output media do not share code beyond reading the same JSON.

## Report contents

### Charts (inline SVG)

Rendered from `aggregate.json`:

- Results by color (win/loss/draw bars).
- Average CPL by phase (opening / middlegame / endgame).
- Move quality counts (blunders / mistakes / inaccuracies).
- Average CPL: wins vs losses vs draws.
- Time trouble summary (moves in TT, blunders in TT, losses with a TT blunder).

New, aimed at the blunder-origin question (derived from `analysis.json`
per-move data, normalized to the player's point of view):

- **Blunder-origin chart:** blunders bucketed by the eval *before* the blunder —
  winning (> +1.5), roughly equal (+/- 1.5), already losing (< -1.5). Answers
  "are my blunders thrown away from good positions, or am I already lost?"
- **Eval-trajectory sparklines:** for each top-blunder game, a small polyline of
  the player's eval across the game with the blunder move marked, so the cliff is
  visible.

### Opening figures

For each opening in `opening_performance`:

- Select one representative game of that opening+color from `analysis.json`.
- Find the FEN at the end of that game's opening phase: take the first move
  whose `phase` is no longer `"opening"` and use its `fen_before` (the position
  reached once the opening is complete). If every move is `"opening"`, use the
  last move's `fen_before`.
- Render that position as an inline `chess.svg` board beside the opening's row
  (record, win%, opening CPL).
- If no representative position is available, render the row without a board
  rather than failing.

### Top-blunders drills

For each entry in `top_blunders`:

- Render a small board of the position just before the move (the `fen_before` is
  already in the data).
- Show the move played, the eval swing, the phase, the result, and the
  chess.com game link.

### Study plan (data scaffold + optional prose)

- The script generates a deterministic, data-driven plan from `aggregate.json`:
  ranked phase priorities (by CPL and blunder counts), the player's specific
  drill positions (FEN + chess.com link from `top_blunders`), and weak openings
  to study (losing records or high opening CPL from `opening_performance`).
- Optional `--tips PATH` flag: if provided, the Markdown at PATH (Claude-authored
  coaching narrative) is injected into a "Coach's notes" block above the
  data-driven plan.
- Without `--tips`, the data-driven plan stands alone, so the script is fully
  runnable on its own.

## Data flow

```
fetch_games.py  --out ./chess-analysis   ->  games.json
analyze_games.py --in ./chess-analysis   ->  analysis.json, aggregate.json
render_charts.py --in ./chess-analysis   ->  ASCII/Markdown dashboard (chat)
render_report.py --in ./chess-analysis [--tips tips.md]
                                         ->  report.html (self-contained)
```

## Error handling

- Missing `aggregate.json` / `analysis.json`: clear error naming the expected
  path and the command that produces them.
- Empty `opening_performance`: render the report without the openings section (or
  with an explanatory note) rather than failing.
- Missing representative position for an opening: omit that board, keep the row.
- Missing `--tips` file path: error if the flag is passed but the file is absent;
  proceed normally if the flag is omitted.

## Testing

New `tests/test_report.py` (deterministic, no network), using fixture JSON:

- HTML contains each expected section heading.
- At least one SVG board (`<svg`) renders for openings and top blunders.
- Blunder-origin buckets sum to the total blunder count.
- Empty `opening_performance` is handled gracefully.
- `--tips` content is injected when provided and absent when not.

## Documentation

- SKILL.md: new step for rendering the HTML report; updated default paths; note
  the optional `--tips` slot and that the report is self-contained.
- CLAUDE.md: architecture note for the new script and the preserved
  stdlib-only invariant of `render_charts.py`; updated local-command examples and
  `.gitignore` mention.

## Delivery / PR sequencing

- Separate from the open count PR (#5, `chore/default-100-games`).
- Own branch `feat/html-report` off `main`, own PR
  (`feat: add self-contained HTML report with visualizations and study plan`).
- Conventional Commit `feat:` => minor version bump via release-please.

## Out of scope (YAGNI)

- Interactive/JS-driven charts or a hosted dashboard.
- PDF export.
- Lichess support.
- Changing the analysis math, CPL/phase heuristics, or the fetcher.
