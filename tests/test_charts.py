"""Unit tests for render_charts ASCII rendering (no engine, no network)."""

import render_charts as rc


def test_bar_proportional():
    assert rc.bar(0, 100, width=10) == ""
    assert rc.bar(100, 100, width=10) == "█" * 10
    assert rc.bar(50, 100, width=10) == "█" * 5


def test_bar_min_one_for_nonzero():
    # a tiny but nonzero value still shows at least one block
    assert rc.bar(1, 1000, width=10) == "█"


def test_bar_zero_max_is_empty():
    assert rc.bar(5, 0, width=10) == ""


def test_bar_clamps_to_width():
    assert len(rc.bar(999, 100, width=10)) == 10


def test_value_bars_aligns_and_skips_none():
    out = rc.render_value_bars([("A", 10), ("BB", None), ("CCC", 5)])
    lines = out.splitlines()
    assert len(lines) == 2  # None row skipped
    assert lines[0].startswith("A  ")
    assert lines[1].startswith("CCC")


def test_results_by_color_winrate():
    agg = {
        "by_color": {
            "white": {"win": 14, "loss": 13, "draw": 0},
            "black": {"win": 12, "loss": 10, "draw": 1},
        },
        "results": {"win": 26, "loss": 23, "draw": 1},
    }
    out = rc.render_results_by_color(agg)
    assert "52%" in out
    assert "26W / 23L / 1D" in out


def test_openings_empty():
    assert "no opening" in rc.render_openings({"opening_performance": []})


def test_build_report_charts_has_all_sections():
    agg = {
        "games_analyzed": 2,
        "chesscom_avg_accuracy": 70.0,
        "by_color": {"white": {"win": 1, "loss": 1, "draw": 0}},
        "results": {"win": 1, "loss": 1, "draw": 0},
        "avg_cpl_by_phase": {"opening": 30, "middlegame": 90, "endgame": 80},
        "move_quality": {
            "blunders": 4,
            "mistakes": 6,
            "inaccuracies": 8,
            "blunders_per_game": 2.0,
            "mistakes_per_game": 3.0,
        },
        "avg_cpl_by_result": {"win": 50, "loss": 95},
        "blunders_by_phase": {
            "middlegame": {"blunder": 4, "mistake": 6, "inaccuracy": 8}
        },
        "time_trouble": {
            "my_moves_in_time_trouble": 5,
            "blunders_in_time_trouble": 1,
            "losses_with_time_trouble_blunder": 1,
            "share_of_blunders_in_time_trouble": 0.25,
        },
        "opening_performance": [],
    }
    out = rc.build_report_charts(agg)
    for heading in (
        "Results by color",
        "by phase",
        "Move quality",
        "wins vs losses",
        "Time trouble",
        "Opening performance",
    ):
        assert heading in out
    # fenced blocks must be balanced
    assert out.count("```") % 2 == 0
