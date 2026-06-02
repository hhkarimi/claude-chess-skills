"""Unit tests for render_report HTML generation (no engine run, no network)."""

import chess

import render_report as rr


def _min_agg():
    return {
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
        "avg_cpl_by_result": {"win": 50, "loss": 95, "draw": 20},
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
    for heading in (
        "Results by color",
        "centipawn loss by phase",
        "Move quality",
        "wins vs losses",
        "Time trouble",
    ):
        assert heading in out
    assert "<svg" in out


def _games_with_blunders():
    # white blundering from a winning (+500) and an equal (+20) position;
    # black blundering from a losing (white +400 => black -400) position.
    return [
        {
            "my_color": "white",
            "url": "https://chess.com/g/1",
            "moves": [
                {"class": "blunder", "eval_before": 500},
                {"class": None, "eval_before": -100},
                {"class": "blunder", "eval_before": 20},
            ],
        },
        {
            # eval_before is already player-POV in analysis.json, so a Black
            # player who is losing has a negative eval_before.
            "my_color": "black",
            "url": "https://chess.com/g/2",
            "moves": [
                {"class": "blunder", "eval_before": -400},
            ],
        },
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


def test_eval_series_uses_stored_player_pov_as_is():
    # analysis.json already stores eval_after in the player's POV, so the values
    # pass through unchanged regardless of color.
    game = {
        "my_color": "black",
        "moves": [
            {"eval_after": 100},
            {"eval_after": -200},
        ],
    }
    assert rr.eval_series(game) == [100, -200]


def test_svg_sparkline_marks_the_blunder_index():
    svg = rr.svg_sparkline([100, 50, -300, -280], mark_index=2)
    assert svg.startswith("<svg")
    assert "<polyline" in svg
    assert "<circle" in svg  # the marked blunder point


def test_opening_position_fen_stops_at_end_of_opening():
    game = {
        "moves": [
            {"phase": "opening", "fen_before": "FEN_OPENING_1"},
            {"phase": "opening", "fen_before": "FEN_OPENING_2"},
            {"phase": "middlegame", "fen_before": "FEN_MIDDLE"},
        ]
    }
    assert rr.opening_position_fen(game) == "FEN_MIDDLE"


def test_opening_position_fen_all_opening_uses_last():
    game = {
        "moves": [
            {"phase": "opening", "fen_before": "A"},
            {"phase": "opening", "fen_before": "B"},
        ]
    }
    assert rr.opening_position_fen(game) == "B"


def test_board_svg_renders_real_svg_from_startpos():
    svg = rr.board_svg(chess.STARTING_FEN, color="white")
    assert "<svg" in svg


def test_section_openings_includes_board_when_game_matches():
    agg = {
        "opening_performance": [
            {
                "opening": "Scotch Game",
                "color": "white",
                "games": 2,
                "win": 2,
                "loss": 0,
                "draw": 0,
                "avg_opening_cpl": 40.0,
            },
        ]
    }

    games = [
        {
            "opening": "Scotch Game",
            "my_color": "white",
            "moves": [
                {"phase": "opening", "fen_before": chess.STARTING_FEN},
                {"phase": "middlegame", "fen_before": chess.STARTING_FEN},
            ],
        }
    ]
    out = rr.section_openings(agg, games)
    assert "Scotch Game" in out
    assert "<svg" in out  # board rendered
    assert "2-0-0" in out


def test_section_openings_empty_is_graceful():
    out = rr.section_openings({"opening_performance": []}, [])
    assert "no opening" in out.lower()
    assert "<svg" not in out


def test_section_top_blunders_renders_boards_and_links():
    agg = {
        "top_blunders": [
            {
                "game_url": "https://chess.com/g/1",
                "move_no": 20,
                "san": "Qxf7",
                "phase": "middlegame",
                "color": "white",
                "result": "loss",
                "raw_swing": 2540,
                "fen_before": chess.STARTING_FEN,
            },
        ]
    }
    out = rr.section_top_blunders(agg)
    assert "Top blunders" in out
    assert "<svg" in out  # board from fen_before
    assert "20. Qxf7" in out
    assert "https://chess.com/g/1" in out
    assert "2540" in out


def test_section_top_blunders_empty_is_graceful():
    out = rr.section_top_blunders({"top_blunders": []})
    assert "no blunders" in out.lower()
    assert "<svg" not in out


def test_md_to_html_handles_headings_bullets_and_paragraphs():
    out = rr.md_to_html("## Focus\n\nWork on tactics.\n\n- one\n- two")
    assert "<h3>Focus</h3>" in out
    assert "<p>Work on tactics.</p>" in out
    assert "<li>one</li>" in out and "<li>two</li>" in out
    assert "<ul>" in out


def test_md_to_html_escapes_html():
    assert "&lt;script&gt;" in rr.md_to_html("<script>")


def test_section_study_plan_ranks_phase_and_lists_drills():
    agg = {
        "avg_cpl_by_phase": {"opening": 30, "middlegame": 95, "endgame": 80},
        "blunders_by_phase": {
            "opening": {"blunder": 2},
            "middlegame": {"blunder": 10},
            "endgame": {"blunder": 7},
        },
        "opening_performance": [
            {
                "opening": "Italian Game",
                "color": "black",
                "games": 3,
                "win": 1,
                "loss": 2,
                "draw": 0,
                "avg_opening_cpl": 78.0,
            },
            {
                "opening": "Scotch Game",
                "color": "white",
                "games": 5,
                "win": 5,
                "loss": 0,
                "draw": 0,
                "avg_opening_cpl": 39.0,
            },
        ],
        "top_blunders": [
            {
                "game_url": "https://chess.com/g/1",
                "move_no": 20,
                "san": "Qxf7",
                "color": "white",
            },
        ],
    }
    out = rr.section_study_plan(agg)
    assert "Study plan" in out
    # middlegame has the worst CPL+blunders, so it should be the top priority
    assert out.index("Middlegame") < out.index("Endgame")
    # weak opening (losing record / high CPL) is flagged, strong one is not
    assert "Italian Game" in out
    assert "Scotch Game" not in out
    # a concrete drill link is included
    assert "https://chess.com/g/1" in out


def test_section_study_plan_injects_coach_notes_when_tips_given():
    out = rr.section_study_plan(
        {"avg_cpl_by_phase": {}}, tips_md="## Hi\n\nFocus here."
    )
    assert "Coach's notes" in out
    assert "Focus here." in out


def test_section_study_plan_no_coach_notes_without_tips():
    out = rr.section_study_plan({"avg_cpl_by_phase": {}})
    assert "Coach's notes" not in out


def test_build_html_full_document_has_every_section():
    agg = _min_agg()
    agg["opening_performance"] = [
        {
            "opening": "Scotch Game",
            "color": "white",
            "games": 2,
            "win": 2,
            "loss": 0,
            "draw": 0,
            "avg_opening_cpl": 40.0,
        },
    ]
    agg["top_blunders"] = [
        {
            "game_url": "https://chess.com/g/1",
            "move_no": 20,
            "san": "Qxf7",
            "phase": "middlegame",
            "color": "white",
            "result": "loss",
            "raw_swing": 2540,
            "fen_before": chess.STARTING_FEN,
        },
    ]
    games = [
        {
            "url": "https://chess.com/g/1",
            "my_color": "white",
            "opening": "Scotch Game",
            "moves": [
                {
                    "move_no": 1,
                    "phase": "opening",
                    "eval_before": 30,
                    "eval_after": 20,
                    "class": None,
                    "fen_before": chess.STARTING_FEN,
                },
                {
                    "move_no": 20,
                    "phase": "middlegame",
                    "eval_before": 541,
                    "eval_after": -1999,
                    "class": "blunder",
                    "fen_before": chess.STARTING_FEN,
                },
            ],
        }
    ]
    html_out = rr.build_html(agg, games, tips_md="## Notes\n\nWatch your queen.")
    for heading in (
        "Charts",
        "Where your blunders come from",
        "Openings",
        "Top blunders",
        "Study plan",
        "Coach's notes",
    ):
        assert heading in html_out, heading
    assert html_out.strip().endswith("</html>")


def test_board_player_one_visible_frame_and_controls():
    frames = [(chess.STARTING_FEN, "start"), (chess.STARTING_FEN, "1. e4")]
    out = rr.board_player(frames)
    assert out.count('class="frame"') == 2
    assert out.count("hidden") == 1  # all but the first frame hidden
    assert out.count("<button") == 4
    assert 'data-cap="start"' in out


def test_board_player_unique_ids_across_calls():
    import re as _re

    f = [(chess.STARTING_FEN, "start")]
    id1 = _re.search(r'id="(bp\d+)"', rr.board_player(f)).group(1)
    id2 = _re.search(r'id="(bp\d+)"', rr.board_player(f)).group(1)
    assert id1 != id2


def test_board_player_empty_is_blank():
    assert rr.board_player([]) == ""


_PGN = "1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 *"


def test_game_frames_opening_range_has_start_plus_moves():
    frames = rr.game_frames(_PGN, start_ply=0, end_ply=3)
    caps = [c for _, c in frames]
    assert caps == ["start", "1. e4", "1...e5", "2. Nf3"]


def test_game_frames_blunder_range_skips_start():
    frames = rr.game_frames(_PGN, start_ply=1, end_ply=6)
    caps = [c for _, c in frames]
    assert caps[0] == "1. e4" and "start" not in caps
    assert len(frames) == 6


def test_opening_end_ply_matches_position():
    # position after 1. e4 e5 2. Nf3 (before 2...Nc6)
    fen = "rnbqkbnr/pppp1ppp/8/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq - 1 2"
    assert rr._opening_end_ply(_PGN, fen) == 3


def test_opening_end_ply_falls_back_to_cap_when_unmatched():
    assert rr._opening_end_ply(_PGN, None, cap=20) == 6  # whole short game, < cap


def test_blunder_ply_locates_move():
    assert rr._blunder_ply(_PGN, 3, "white", "Bb5") == 5
    assert rr._blunder_ply(_PGN, 3, "white", "Qh5") is None


_OPEN_PGN = "1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 *"


def test_section_openings_interactive_when_pgn_present():
    agg = {
        "opening_performance": [
            {
                "opening": "Ruy Lopez",
                "color": "white",
                "games": 2,
                "win": 2,
                "loss": 0,
                "draw": 0,
                "avg_opening_cpl": 30.0,
            },
        ]
    }
    games = [
        {
            "opening": "Ruy Lopez",
            "my_color": "white",
            "url": "u1",
            "moves": [{"phase": "opening", "fen_before": chess.STARTING_FEN}],
        }
    ]
    out = rr.section_openings(agg, games, {"u1": _OPEN_PGN})
    assert 'class="player' in out
    assert out.count('class="frame"') >= 3


def test_section_openings_falls_back_to_static_without_pgn():
    agg = {
        "opening_performance": [
            {
                "opening": "Ruy Lopez",
                "color": "white",
                "games": 2,
                "win": 2,
                "loss": 0,
                "draw": 0,
                "avg_opening_cpl": 30.0,
            },
        ]
    }
    games = [
        {
            "opening": "Ruy Lopez",
            "my_color": "white",
            "url": "u1",
            "moves": [{"phase": "middlegame", "fen_before": chess.STARTING_FEN}],
        }
    ]
    out = rr.section_openings(agg, games)
    assert "<svg" in out
    assert 'class="player' not in out


def test_section_top_blunders_interactive_when_pgn_present():
    agg = {
        "top_blunders": [
            {
                "game_url": "u1",
                "move_no": 3,
                "san": "Bb5",
                "phase": "opening",
                "color": "white",
                "result": "loss",
                "raw_swing": 900,
                "fen_before": chess.STARTING_FEN,
            },
        ]
    }
    out = rr.section_top_blunders(agg, {"u1": _OPEN_PGN})
    assert 'class="player' in out
    assert "u1" in out


def test_build_html_emits_board_script_once():
    agg = _min_agg()
    agg["top_blunders"] = [
        {
            "game_url": "u1",
            "move_no": 3,
            "san": "Bb5",
            "phase": "opening",
            "color": "white",
            "result": "loss",
            "raw_swing": 900,
            "fen_before": chess.STARTING_FEN,
        },
    ]
    raw = [{"url": "u1", "pgn": _OPEN_PGN}]
    out = rr.build_html(agg, [], raw_games=raw)
    assert out.count("function chessStep") == 1
    assert 'class="player' in out


def test_term_wraps_with_tooltip_and_glossary_anchor():
    out = rr._term("cpl")
    assert 'href="#glossary-cpl"' in out
    assert "title=" in out
    assert "CPL" in out


def test_section_glossary_has_anchor_targets():
    out = rr.section_glossary()
    assert 'id="glossary"' in out
    assert 'id="glossary-cpl"' in out
    assert 'id="glossary-blunder"' in out
    assert "Glossary" in out


def test_build_html_includes_glossary():
    out = rr.build_html(_min_agg(), [])
    assert 'id="glossary"' in out


def test_section_top_blunders_includes_sparkline_from_games():
    agg = {
        "top_blunders": [
            {
                "game_url": "u1",
                "move_no": 2,
                "san": "Qxf7",
                "phase": "middlegame",
                "color": "white",
                "result": "loss",
                "raw_swing": 2000,
                "fen_before": chess.STARTING_FEN,
            },
        ]
    }
    games = [
        {
            "url": "u1",
            "my_color": "white",
            "moves": [
                {"move_no": 1, "eval_after": 500},
                {"move_no": 2, "eval_after": -1500},
            ],
        }
    ]
    out = rr.section_top_blunders(agg, games=games)
    assert "<polyline" in out  # sparkline rendered inside the blunder card
    assert "Top blunders" in out


def test_section_practice_always_includes_puzzles():
    out = rr.section_practice(
        {"avg_cpl_by_phase": {}, "blunders_by_phase": {}, "opening_performance": []}
    )
    assert "lichess.org/training" in out
    assert "Where to practice" in out


def test_section_practice_includes_endgame_when_weak():
    agg = {
        "avg_cpl_by_phase": {"opening": 10, "middlegame": 20, "endgame": 95},
        "blunders_by_phase": {"endgame": {"blunder": 30}},
        "opening_performance": [],
    }
    assert "lichess.org/practice" in rr.section_practice(agg)


def test_section_practice_skips_endgame_when_strong():
    agg = {
        "avg_cpl_by_phase": {"opening": 90, "middlegame": 80, "endgame": 10},
        "blunders_by_phase": {
            "opening": {"blunder": 30},
            "middlegame": {"blunder": 20},
        },
        "opening_performance": [],
    }
    assert "lichess.org/practice" not in rr.section_practice(agg)


def test_section_practice_names_weakest_opening():
    agg = {
        "avg_cpl_by_phase": {},
        "blunders_by_phase": {},
        "opening_performance": [
            {
                "opening": "Italian Game",
                "color": "black",
                "games": 3,
                "win": 1,
                "loss": 2,
                "draw": 0,
                "avg_opening_cpl": 80.0,
            },
        ],
    }
    out = rr.section_practice(agg)
    assert "lichess.org/opening" in out and "Italian Game" in out


def test_section_study_plan_includes_practice():
    assert "Where to practice" in rr.section_study_plan({"avg_cpl_by_phase": {}})


def test_build_html_v2_full_document():
    agg = _min_agg()
    agg["opening_performance"] = [
        {
            "opening": "Ruy Lopez",
            "color": "white",
            "games": 2,
            "win": 2,
            "loss": 0,
            "draw": 0,
            "avg_opening_cpl": 30.0,
        },
    ]
    agg["top_blunders"] = [
        {
            "game_url": "u1",
            "move_no": 3,
            "san": "Bb5",
            "phase": "opening",
            "color": "white",
            "result": "loss",
            "raw_swing": 900,
            "fen_before": chess.STARTING_FEN,
        },
    ]
    games = [
        {
            "opening": "Ruy Lopez",
            "my_color": "white",
            "url": "u1",
            "moves": [
                {
                    "move_no": 3,
                    "phase": "opening",
                    "eval_before": 300,
                    "eval_after": -600,
                    "class": "blunder",
                    "fen_before": chess.STARTING_FEN,
                }
            ],
        }
    ]
    raw = [{"url": "u1", "pgn": "1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 *"}]
    out = rr.build_html(agg, games, raw_games=raw, tips_md="## Notes\n\nWatch checks.")
    for needle in (
        'class="player',
        "function chessStep",
        "Glossary",
        "Where to practice",
        "Coach's notes",
        "<polyline",
    ):
        assert needle in out, needle
    assert out.count("function chessStep") == 1
    assert out.strip().endswith("</html>")
