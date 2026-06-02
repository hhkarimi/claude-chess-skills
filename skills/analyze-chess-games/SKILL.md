---
name: analyze-chess-games
description: Use when the user wants to improve at chess by analyzing their recent chess.com games — finding recurring blunders, weak openings, bad phases (opening/middlegame/endgame), or time-trouble losses, and getting specific, prioritized practice advice. Triggers on "analyze my chess games", "how can I improve my chess", "review my chess.com games".
---

# Analyze chess.com games

Pull a player's recent chess.com games, evaluate every move with Stockfish, and
turn the engine data into a stats dashboard plus a short, prioritized list of
improvement tips with concrete examples.

This is a two-script pipeline (`fetch_games.py` -> `analyze_games.py`) plus a
report you write from the resulting `aggregate-<username>.json`. Output is
namespaced per username under `./chess-analysis/<username>/`.

## When to use

- The user wants concrete, data-backed feedback on how to get better at chess.
- The user wants to know their recurring mistakes, weak openings, or whether they
  lose in the opening / middlegame / endgame.
- The user suspects time trouble or specific blunders are costing them games.

## When NOT to use

- The user wants analysis of a single specific position or game in depth — load
  that PGN into Stockfish directly instead; this skill is about patterns across
  many games.
- The player's chess.com archives are private or the account is on Lichess — the
  fetcher only reads chess.com's public Published-Data API. (For Lichess, adapt
  the fetcher to its API.)

## How to use

### 1. Get the username

Ask the user for their **exact chess.com username** if they haven't given it.
Pass it as a CLI argument every run. Do not hardcode or commit it.

### 2. Fetch recent games

PEP 723 inline-deps Python — run with `uv run`. Output is namespaced per
username: everything lands in `./chess-analysis/<username>/` so multiple players
don't clobber each other.

```bash
uv run scripts/fetch_games.py <username> [--count 100] [--out ./chess-analysis]
```

Writes `chess-analysis/<username>/games-<username>.json`
(`{username, count, games: [...]}`). Each game carries the PGN plus metadata:
color, normalized result (win/loss/draw), time class/control, ratings, and
chess.com's own accuracy score when present.

### 3. Analyze with Stockfish

Point `--in` at the user's subdir; the analyzer reads the username back out of
the games file and writes its outputs with the same suffix.

```bash
uv run scripts/analyze_games.py --in ./chess-analysis/<username> [--depth 12] [--max-games N]
```

If Stockfish is not on PATH, the script installs it with `brew install stockfish`
(pass `--no-install` to disable, or `--stockfish PATH` to point at a binary).

Writes (alongside the games file):
- `analysis-<username>.json` — per-game, per-move detail for the player's moves
  (CPL, class, phase, time-trouble flag, eval before/after, FEN).
- `aggregate-<username>.json` — the summary you build the report from.

`--depth 12` analyzes ~100 games in a few minutes. Lower it (`--depth 8`) for a
quick pass, raise it (`--depth 16`) for sharper blunder detection at more cost.
Use `--max-games` to spot-check quickly.

### 4. Render the charts

Generate the visual dashboard from `aggregate-<username>.json`:

```bash
uv run scripts/render_charts.py --in ./chess-analysis/<username>
```

This prints a Markdown block with two parts: **charts** (ASCII bar charts in
fenced code blocks — results by color, CPL by phase, move quality, wins-vs-losses
CPL, time trouble) and **tables** (Markdown tables — mistakes by phase, opening
performance, and top blunders with chess.com game links). Stdlib only — no
dependencies.

### 5. Render the HTML report (richer)

Generate a self-contained HTML report with SVG charts, per-opening board
diagrams, a blunder-origin chart and per-blunder eval-swing sparklines, and a
study plan.

**Always author the Coach's notes first.** Write the prioritized coaching prose
(step 6, part B) to `chess-analysis/<username>/tips-<username>.md`, then render —
the renderer auto-injects that file as a "Coach's notes" block at the top of the
study plan, so it is always included. Coach's notes are Claude-authored and the
most valuable part of the report; the script cannot generate them. If you render
without a tips file, the renderer still succeeds but prints a `warning:` reminding
you the report has no Coach's notes.

```bash
# 1) write tips-<username>.md (see step 6B), then:
uv run scripts/render_report.py --in ./chess-analysis/<username>
# (--tips path/to/file.md overrides the auto-detected tips-<username>.md)
```

Writes `report-<username>.html` to the input dir — one file, no external assets,
opens in any browser offline. The study plan is generated from the data; your
`tips-<username>.md` is injected as the "Coach's notes" block at the top of it.
Only the `python-chess` dependency
is needed (already used by the analyzer), and `render_charts.py` is unaffected.
The report is interactive: opening and top-blunder boards step through the moves
(First/Prev/Next/Last) and each blunder card shows its evaluation-swing chart;
jargon has hover tooltips with a Glossary at the bottom; and the study plan links
to lichess practice resources matched to your weaknesses. The renderer also reads
`games-<username>.json` for move-by-move replay — if it is absent, boards fall
back to a single static diagram. Opening boards stop at the move that defines each opening
(matched against a bundled openings book, `openings_book.txt`, derived from
lichess chess-openings, CC0) and show the engine score in pawns from White's
point of view at each step.

### 6. Write the report

Read `aggregate-<username>.json` and produce **two parts**:

**A. Stats dashboard** — paste the `render_charts.py` output verbatim. Keep the
fenced code blocks intact (they preserve the bar alignment) and leave the Markdown
tables unfenced so they render as tables. Do not redraw the charts or tables by
hand.

**B. Prioritized tips** — the heart of the output. Rank the user's weaknesses by
how much they actually cost, and for each give a concrete example and a fix:
- Lead with the highest-impact pattern (e.g. "middlegame blunders cost you most"
  if `avg_cpl_by_phase['middlegame']` dominates, or "you collapse in time trouble"
  if a large `share_of_blunders_in_time_trouble`).
- Cite specific games from `top_blunders`: the move number, the move played, the
  eval swing, and the chess.com game link. These links are the user's payoff —
  always include them so they can replay the position.
- Flag weak openings from `opening_performance` (losing records or high opening
  CPL) and name a concrete study target.
- End with a short, focused practice plan (2-4 items), not a generic checklist.

Keep the tips specific and grounded in this player's data. Do not invent
weaknesses the numbers don't support.

Save part B to `chess-analysis/<username>/tips-<username>.md` so the HTML report
(step 5) picks it up as Coach's notes. The same prose serves both outputs: the
Markdown chat report here and the "Coach's notes" block in the HTML report.

## Requirements

- `uv` (Astral's Python project manager): `brew install uv`
- `stockfish` — auto-installed via Homebrew on first analyze run if missing.
- `python-chess` is declared in the analyzer's PEP 723 header; `uv` fetches it.

## Troubleshooting

- **`no public profile for '<user>'`** — username misspelled, or the account's
  archives are private. Confirm the exact chess.com username.
- **Fewer than 100 games returned** — the account simply hasn't played that many;
  the report uses whatever is available.
- **Analysis is slow** — lower `--depth`, or use `--max-games` for a quick look.
  Depth 12 is a good accuracy/speed balance; depth 8 is roughly 3x faster.
- **`opening_performance` is empty** — openings are only summarized when the same
  opening+color appears 2+ times; with few games or a varied repertoire it can be
  sparse. Rely on `top_blunders` and phase CPL instead.
- **Stockfish install refused / offline** — install manually from
  https://stockfishchess.org/download/ and pass `--stockfish /path/to/stockfish`.
