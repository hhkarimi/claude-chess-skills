"""Unit tests for analyze_games engine-free logic (no Stockfish required)."""

import chess

import analyze_games as az


def test_classify_thresholds():
    assert az.classify(0) is None
    assert az.classify(49) is None
    assert az.classify(50) == "inaccuracy"
    assert az.classify(99) == "inaccuracy"
    assert az.classify(100) == "mistake"
    assert az.classify(299) == "mistake"
    assert az.classify(300) == "blunder"
    assert az.classify(900) == "blunder"


def test_base_seconds():
    assert az.base_seconds("600") == 600
    assert az.base_seconds("600+5") == 600
    assert az.base_seconds("180+2") == 180
    assert az.base_seconds("1/259200") is None  # daily
    assert az.base_seconds(None) is None
    assert az.base_seconds("garbage") is None


def test_phase_starting_position_is_opening():
    assert az.phase_of(chess.Board()) == "opening"


def test_phase_bare_kings_is_endgame():
    assert az.phase_of(chess.Board("4k3/8/8/8/8/8/8/4K3 w - - 0 40")) == "endgame"


def test_phase_king_and_rook_endgame():
    assert az.phase_of(chess.Board("4k3/8/8/8/8/8/8/R3K3 w - - 0 40")) == "endgame"


def test_opening_name_from_eco_url():
    headers = {
        "ECOUrl": "https://www.chess.com/openings/Sicilian-Defense-Najdorf",
        "ECO": "B90",
    }
    assert az._opening_name(headers) == "Sicilian Defense Najdorf"


def test_opening_name_falls_back_to_eco():
    assert az._opening_name({"ECO": "C40"}) == "C40"


def _game(color, result, opening, moves):
    return {
        "index": 0,
        "url": "u",
        "my_color": color,
        "result": result,
        "my_result_raw": result,
        "time_class": "rapid",
        "my_rating": 800,
        "opp_rating": 800,
        "my_accuracy": 80.0,
        "eco": "C40",
        "opening": opening,
        "moves": moves,
    }


def _move(cpl, phase="middlegame", cls=None, tt=False, move_no=10):
    return {
        "move_no": move_no,
        "san": "Qh5",
        "phase": phase,
        "cpl": cpl,
        "raw_swing": cpl,
        "class": cls,
        "in_time_trouble": tt,
        "clock": 12.0 if tt else 300.0,
        "eval_before": 20,
        "eval_after": 20 - cpl,
        "fen_before": "startpos",
    }


def test_build_aggregate_counts_and_rates():
    per_game = [
        _game(
            "white",
            "win",
            "Italian Game",
            [_move(10, "opening"), _move(400, "middlegame", "blunder")],
        ),
        _game(
            "black",
            "loss",
            "Italian Game",
            [
                _move(120, "middlegame", "mistake", tt=True),
                _move(350, "middlegame", "blunder", tt=True),
            ],
        ),
    ]
    agg = az.build_aggregate(per_game)
    assert agg["games_analyzed"] == 2
    assert agg["results"] == {"win": 1, "loss": 1}
    assert agg["move_quality"]["blunders"] == 2
    assert agg["move_quality"]["mistakes"] == 1
    assert agg["move_quality"]["blunders_per_game"] == 1.0
    # one of the two blunders was in time trouble
    assert agg["time_trouble"]["blunders_in_time_trouble"] == 1
    assert agg["time_trouble"]["losses_with_time_trouble_blunder"] == 1
    assert agg["time_trouble"]["share_of_blunders_in_time_trouble"] == 0.5


def test_build_aggregate_top_blunders_sorted_by_swing():
    per_game = [
        _game(
            "white",
            "loss",
            "X",
            [_move(300, "middlegame", "blunder"), _move(800, "middlegame", "blunder")],
        ),
    ]
    agg = az.build_aggregate(per_game)
    swings = [b["raw_swing"] for b in agg["top_blunders"]]
    assert swings == sorted(swings, reverse=True)
    assert agg["top_blunders"][0]["raw_swing"] == 800


def test_build_aggregate_opening_needs_two_games():
    # opening seen only once -> excluded from summary
    per_game = [_game("white", "win", "Rare Line", [_move(10, "opening")])]
    agg = az.build_aggregate(per_game)
    assert agg["opening_performance"] == []
