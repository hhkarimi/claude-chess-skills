# CLAUDE.md

Repo-specific guidance for Claude Code sessions working in this plugin.

## Branch protection

- `main` is protected. No direct pushes — all changes via PR.
- PRs require CODEOWNER approval (= @hhkarimi) and passing CI (`lint`, `validate`).
- Squash-merge only — the PR title becomes the squash commit message.

## Commit conventions

Use **Conventional Commits** in PR titles. release-please reads these to decide
version bumps:

| Prefix | release-please effect |
|---|---|
| `feat:` | minor version bump (0.1.0 → 0.2.0) |
| `fix:` | patch bump (0.1.0 → 0.1.1) |
| `feat!:` or `BREAKING CHANGE:` in body | major bump (0.1.0 → 1.0.0) |
| `chore:`, `docs:`, `ci:`, `refactor:`, `test:`, `style:` | no version bump |

When in doubt, prefer `chore:` or `docs:` for non-user-visible changes.

## Architecture

One skill, a two-stage pipeline plus a report you (Claude) write:

1. **`fetch_games.py`** — reads chess.com's public Published-Data API. Resolves
   the player's monthly archive list, walks it newest-first, and writes the last
   N games (PGN + metadata) to `games.json`. Stdlib only (urllib), no deps. The
   username is a CLI arg — never hardcode or commit it.

2. **`analyze_games.py`** — runs each game through Stockfish via `python-chess`.
   Uses the efficient one-eval-per-position sweep: evaluate every position once
   from White's POV, then CPL of a move = eval(before) − eval(after) in the
   mover's POV, floored at 0. Classifies moves (inaccuracy/mistake/blunder by
   CPL), tags phase, flags time trouble from `[%clk]` tags, and writes
   `analysis.json` (per-move) + `aggregate.json` (summary + top blunders).
   Auto-installs Stockfish via `brew` if missing.

3. **Report** — Claude reads `aggregate.json` and writes the stats dashboard +
   prioritized tips. See [SKILL.md](skills/analyze-chess-games/SKILL.md) step 4
   for exactly which fields drive which part of the report. **Always include the
   chess.com game links from `top_blunders`** — they're the user's payoff: a tip
   they can't replay is half a tip.

4. **`render_report.py`** — an optional, additive renderer (PEP 723 dep:
   `python-chess` for `chess.svg` board diagrams) that turns `aggregate.json` +
   `analysis.json` into a single self-contained `report.html`: inline CSS,
   hand-rolled inline SVG charts, per-opening board figures, blunder-origin and
   eval-trajectory visualizations, and a data-driven study plan (with an optional
   `--tips` Markdown slot for Claude-authored coaching). `render_charts.py` stays
   stdlib-only; the HTML renderer is the only place `python-chess` is needed for
   presentation.

### Key invariants

- **CPL math**: evals are clamped to ±`EVAL_CAP` (mate included) so one
  catastrophe can't dominate average CPL; per-move CPL is capped at `CPL_CAP` for
  averaging, while `raw_swing` keeps the uncapped value used to rank top blunders.
- **Phase heuristic** (`phase_of`): by non-pawn/non-king material count — endgame
  at ≤6 such pieces, opening while ≤ move 10 and ≥12 pieces, else middlegame.
- **Opening summary** only includes an opening+color seen 2+ times, so it stays
  meaningful on small samples.
- **Time trouble**: a move is in time trouble when the mover's remaining clock is
  ≤ max(30s, 10% of base time). Requires `[%clk]` tags (chess.com live games have
  them; daily games may not).

## Local commands

```bash
cd skills/analyze-chess-games/scripts
uv run fetch_games.py <username> --count 100    # fetch
uv run analyze_games.py --depth 12              # analyze
uv run render_report.py --in ./chess-analysis   # self-contained HTML report

# from repo root — same checks CI runs
uvx ruff check .
uvx ruff format --check .
python3 tests/validate_skills.py
uv run --with chess --with pytest pytest tests -v
```

## Releases

[release-please](https://github.com/googleapis/release-please) watches `main` for
Conventional Commits and opens a `chore(main): release vX.Y.Z` PR. Merging it
tags and releases. `.claude-plugin/plugin.json` and `.release-please-manifest.json`
versions are bumped automatically — keep them in sync (release-please does this).

## Things to NOT do

- **Don't commit usernames or game data.** `.gitignore` excludes `games*.json`,
  `analysis*.json`, `aggregate*.json`, and `*.pgn`, but don't add them manually
  and don't paste a real username into code, tests, or fixtures.
- Don't bypass branch protection without a stated reason.
- Don't put network calls in the analyzer or engine calls in the fetcher — keep
  the two stages cleanly separated so each is testable on its own.
- Don't introduce new top-level directories without considering plugin-install
  behavior. The only directory guaranteed-present in an installed plugin is
  `.claude-plugin/`.
