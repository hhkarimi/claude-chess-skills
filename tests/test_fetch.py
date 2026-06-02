"""Unit tests for fetch_games pure helpers (no network)."""

import fetch_games as fg


def test_normalize_result_win():
    assert fg._normalize_result("win") == "win"


def test_normalize_result_draws():
    for code in ("agreed", "repetition", "stalemate", "insufficient", "50move"):
        assert fg._normalize_result(code) == "draw"


def test_normalize_result_losses():
    for code in ("checkmated", "resigned", "timeout", "abandoned", "lose"):
        assert fg._normalize_result(code) == "loss"


def _raw_game(white_user, black_user):
    return {
        "url": "https://www.chess.com/game/live/1",
        "end_time": 1,
        "time_class": "rapid",
        "time_control": "600",
        "rated": True,
        "rules": "chess",
        "eco": "https://www.chess.com/openings/X",
        "pgn": '[White "%s"]\n[Black "%s"]\n\n1. e4 e5 1-0' % (white_user, black_user),
        "accuracies": {"white": 90.0, "black": 70.0},
        "white": {"username": white_user, "rating": 800, "result": "win"},
        "black": {"username": black_user, "rating": 790, "result": "resigned"},
    }


def test_shape_game_identifies_color_case_insensitive():
    g = fg._shape_game(_raw_game("HughForHugh", "rival"), "hughforhugh", index=0)
    assert g["my_color"] == "white"
    assert g["result"] == "win"
    assert g["my_accuracy"] == 90.0
    assert g["opp_accuracy"] == 70.0
    assert g["opp_username"] == "rival"


def test_shape_game_as_black():
    g = fg._shape_game(_raw_game("rival", "Player"), "player", index=3)
    assert g["my_color"] == "black"
    assert g["result"] == "loss"  # black "resigned"
    assert g["index"] == 3


def test_shape_game_missing_pgn_returns_none():
    raw = _raw_game("a", "b")
    del raw["pgn"]
    assert fg._shape_game(raw, "a", index=0) is None


def test_shape_game_username_absent_returns_none():
    assert fg._shape_game(_raw_game("a", "b"), "someone_else", index=0) is None
