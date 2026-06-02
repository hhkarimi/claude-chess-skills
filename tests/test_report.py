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
