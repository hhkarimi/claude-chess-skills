# Contributing

Thanks for helping improve `claude-chess-skills`.

## Ground rules

- `main` is protected. Open a PR; CI and a CODEOWNER review must pass.
- Use [Conventional Commits](https://www.conventionalcommits.org/) in your PR
  title — release-please uses them to version releases (see [CLAUDE.md](CLAUDE.md)).
- **Never commit a chess.com username or fetched game data.** These are personal.
  `.gitignore` already excludes the scratch output; don't force them in or bake a
  real username into code or tests. Use made-up usernames in fixtures.

## Local setup

You need [`uv`](https://github.com/astral-sh/uv). Stockfish is auto-installed by
the analyzer on first run, or `brew install stockfish` yourself.

```bash
# run the pipeline
cd skills/analyze-chess-games/scripts
uv run fetch_games.py <username> --count 50
uv run analyze_games.py --depth 12
```

## Before you push

Run the same checks CI runs:

```bash
uvx ruff check .
uvx ruff format --check .
python3 tests/validate_skills.py
uv run --with chess --with pytest pytest tests -v
```

## Adding a new skill

1. Create `skills/<skill-name>/SKILL.md` with `name` and `description`
   frontmatter (the validator enforces this).
2. Put scripts under `skills/<skill-name>/scripts/` as PEP 723 inline-deps Python.
3. Add tests under `tests/` for any non-trivial pure logic. Tests must not require
   network access or a real account — test pure functions and use synthetic data.

## Reporting bugs

Open an issue with the exact command you ran (omit your username if you like),
expected vs actual behavior, your OS, `uv --version`, and your Stockfish version.
