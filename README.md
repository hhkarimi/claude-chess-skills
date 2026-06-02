# claude-chess-skills

A [Claude Code](https://claude.com/claude-code) plugin that analyzes your recent
chess.com games with Stockfish and turns them into specific, prioritized advice
on how to improve.

It pulls your last N games from chess.com's public API, has Stockfish evaluate
every move, then produces a stats dashboard plus a short list of your
highest-impact weaknesses — each with concrete example positions (linked back to
the game on chess.com) and a focused practice plan.

## What you get

- **Stats dashboard** — record by color, average centipawn loss by phase
  (opening / middlegame / endgame), blunder and mistake rates, win-vs-loss
  accuracy gap, time-trouble frequency, and opening win/loss records.
- **Prioritized tips** — your recurring weaknesses ranked by how much they
  actually cost you, with specific games to review and a 2-4 item practice plan.

## Skills

| Skill | What it does |
|---|---|
| [`analyze-chess-games`](skills/analyze-chess-games/SKILL.md) | Fetch chess.com games, analyze with Stockfish, report improvement tips |

## Requirements

- [`uv`](https://github.com/astral-sh/uv) — `brew install uv`
- [Stockfish](https://stockfishchess.org/) — auto-installed via Homebrew on first
  run if missing (`brew install stockfish`)

Both scripts are PEP 723 inline-deps Python; `uv run` fetches `python-chess`
automatically.

## Usage

From inside Claude Code, just ask: *"analyze my last 50 chess.com games and tell
me how to improve."* Claude runs the pipeline and writes the report.

Manually:

```bash
cd skills/analyze-chess-games/scripts

# 1. Fetch your recent games (public data; username is the only input)
uv run fetch_games.py <your-username> --count 50

# 2. Analyze every move with Stockfish
uv run analyze_games.py --depth 12

# 3. Render the inline ASCII chart dashboard (results, CPL by phase, openings, ...)
uv run render_charts.py

# aggregate.json also holds the top blunders the prioritized tips are built from
```

Output lands in `/tmp/chess/` by default (`games.json`, `analysis.json`,
`aggregate.json`).

## Privacy

Your username is a command-line argument, never stored in the repo. Fetched games
and analysis are written to a scratch directory and are excluded by
`.gitignore`. Don't commit game archives or usernames.

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) and [CLAUDE.md](CLAUDE.md). CI runs ruff
lint/format, a SKILL.md frontmatter validator, and pytest on every PR.

## License

MIT — see [LICENSE](LICENSE).
