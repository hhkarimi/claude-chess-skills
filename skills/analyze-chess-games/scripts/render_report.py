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
