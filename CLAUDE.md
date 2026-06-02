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
   N games (PGN + metadata) to `chess-analysis/<username>/games-<username>.json`.
   Stdlib only (urllib), no deps. The username is a CLI arg — never hardcode or
   commit it.

2. **`analyze_games.py`** — runs each game through Stockfish via `python-chess`.
   Uses the efficient one-eval-per-position sweep: evaluate every position once
   from White's POV, then CPL of a move = eval(before) − eval(after) in the
   mover's POV, floored at 0. Classifies moves (inaccuracy/mistake/blunder by
   CPL), tags phase, flags time trouble from `[%clk]` tags, and writes
   `analysis-<username>.json` (per-move) + `aggregate-<username>.json` (summary +
   top blunders) into the same `--in` dir. Auto-installs Stockfish via `brew` if
   missing.

3. **Report** — Claude reads `aggregate-<username>.json` and writes the stats dashboard +
   prioritized tips. See [SKILL.md](skills/analyze-chess-games/SKILL.md) step 4
   for exactly which fields drive which part of the report. **Always include the
   chess.com game links from `top_blunders`** — they're the user's payoff: a tip
   they can't replay is half a tip.

4. **`render_report.py`** — an optional, additive renderer (PEP 723 dep:
   `python-chess` for `chess.svg` board diagrams) that turns `aggregate-<username>.json` +
   `analysis-<username>.json` into a single self-contained `report-<username>.html`: inline CSS,
   hand-rolled inline SVG charts, per-opening board figures, a blunder-origin
   chart with per-blunder eval-swing sparklines, and a data-driven study plan (with an optional
   `--tips` Markdown slot for Claude-authored coaching). `render_charts.py` stays
   stdlib-only; the HTML renderer is the only place `python-chess` is needed for
   presentation. It also reads `games-<username>.json` (full PGN) to build click-through board steppers for
   openings and blunders (one small inline vanilla-JS stepper, still no CDN/library),
   shows an eval-swing sparkline per blunder, and renders a glossary plus tailored
   lichess practice links. The analyzer also emits a per-game `opening_line` (san +
   White-POV eval) truncated at the deepest position found in the vendored
   `openings_book.txt` (lichess chess-openings, CC0); the report's opening steppers
   render that line with a CP score per move and fall back to the full-PGN stepper
   when `opening_line` is absent.

### Key invariants

- **Per-user output layout**: every stage namespaces by username. `fetch` writes
  `chess-analysis/<username>/games-<username>.json`; `analyze` and `render` read
  the username back out of the games payload and read/write the matching
  `-<username>` suffix in the same dir. So `--in` points at one user's subdir
  (`chess-analysis/<username>`), and the scripts refuse a dir that holds more than
  one user's files rather than guess.
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
uv run fetch_games.py <username> --count 100              # -> chess-analysis/<username>/
uv run analyze_games.py --in ./chess-analysis/<username> --depth 12
uv run render_report.py --in ./chess-analysis/<username>  # self-contained HTML report

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

## Sample output

`docs/sample-report.html` is a committed example of the HTML report, generated
from a real ~900-rated public chess.com account with `render_report.py` run
**without** `--tips` (so it is the deterministic script output, no Claude-authored
coaching). It contains no usernames — only public game-ID links.

**Keep it current:** any PR that changes the report's output (`render_report.py`,
or the `analysis-<username>.json`/`aggregate-<username>.json` fields the report
reads) MUST regenerate this file in the same PR, and confirm no username leaked
into it. Regenerate with (output lands in `/tmp/sample/<~900-user>/`):

```bash
uv run skills/analyze-chess-games/scripts/fetch_games.py <~900-user> --out /tmp/sample
uv run skills/analyze-chess-games/scripts/analyze_games.py --in /tmp/sample/<~900-user> --depth 12
uv run skills/analyze-chess-games/scripts/render_report.py --in /tmp/sample/<~900-user>
cp /tmp/sample/<~900-user>/report-*.html docs/sample-report.html   # then grep it for any username
```

## Things to NOT do

- **Don't commit usernames or game data.** `.gitignore` excludes `games*.json`,
  `analysis*.json`, `aggregate*.json`, and `*.pgn`, but don't add them manually
  and don't paste a real username into code, tests, or fixtures. The one allowed
  exception is `docs/sample-report.html` (see "Sample output"): it is anonymized
  (no usernames — verify before committing) and links only to public chess.com
  game IDs.
- Don't bypass branch protection without a stated reason.
- Don't put network calls in the analyzer or engine calls in the fetcher — keep
  the two stages cleanly separated so each is testable on its own.
- Don't introduce new top-level directories without considering plugin-install
  behavior. The only directory guaranteed-present in an installed plugin is
  `.claude-plugin/`.
