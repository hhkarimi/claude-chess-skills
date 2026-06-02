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
