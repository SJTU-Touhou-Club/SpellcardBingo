"""Flask server for Spellcard Bingo (online mode).

Endpoints:
- GET  /lobby         -> serve lobby page
- POST /api/lobby/join -> { room, team, mode, pool } -> create/join room, redirect to game
- GET  /              -> require ?room= & ?team=(red|blue|observer), else redirect to /lobby
- GET  /state         -> ?room= & ?team= -> full state payload (observer allowed)
- POST /click         -> ?room= & ?team= -> apply click for team (observer forbidden)
- POST /hp            -> ?room= & ?team=, body { team, delta } -> adjust HP (observer forbidden)
- POST /reset         -> ?room= & ?team= -> reset room (observer forbidden)
- GET  /events/<room_id> -> SSE stream for room
"""

import argparse
import queue
import os

from flask import Flask, jsonify, request, send_from_directory, redirect
from flask import Response
from typing import Dict, List, Tuple

from defs import (
    Team,
    CellState,
    color_mapping,
    max_hp,
    show_reset_button,
    SPELLCARD_POOLS,
    DEFAULT_SPELLCARD_POOL,
    max_banned_works_per_player,
)
import state as S
import calc_score as CS

app = Flask(__name__, static_folder="static", static_url_path="")
VALID_CLIENT_TEAMS = ("red", "blue", "observer")

# SSE event queues per room
event_queues: Dict[str, list] = {}


def event_stream(q: "queue.Queue[str]"):
    while True:
        msg = q.get()
        yield f"data: {msg}\n\n"


def broadcast(room_id: str, msg: str) -> None:
    for q in event_queues.get(room_id, []):
        try:
            q.put(msg)
        except Exception:
            pass


def _enum_from_str_team(team_str: str) -> Team:
    s = (team_str or "").lower()
    if s == Team.RED.value:
        return Team.RED
    if s == Team.BLUE.value:
        return Team.BLUE
    raise ValueError(f"Invalid team: {team_str}")


def _normalize_client_team(team_str: str) -> str:
    s = (team_str or "").lower().strip()
    if s not in VALID_CLIENT_TEAMS:
        raise ValueError(f"Invalid team: {team_str}")
    return s


def _card_payload(room: S.BingoRoomState) -> List[List[Dict]]:
    n = room.size
    grid: List[List[Dict]] = []
    for r in range(n):
        row: List[Dict] = []
        for c in range(n):
            rec = room.get_spellcard((r, c))
            row.append({
                "name": str(rec.get("name", "")),
                "score": int(rec.get("score", 0)),
                "index": str(rec.get("index", "")),
                "comment": str(rec.get("comment", "")),
            })
        grid.append(row)
    return grid


def _cells_payload(room: S.BingoRoomState) -> Dict[str, List[List[str]]]:
    n = room.size

    def team_grid(team: Team) -> List[List[str]]:
        g: List[List[str]] = []
        d = room.team_cell_state_dict[team]
        for r in range(n):
            row: List[str] = []
            for c in range(n):
                row.append(d[(r, c)].value)
            g.append(row)
        return g

    return {
        Team.RED.value: team_grid(Team.RED),
        Team.BLUE.value: team_grid(Team.BLUE),
    }


def _scores_payload(room: S.BingoRoomState) -> Dict[str, int]:
    if not room.is_board_ready():
        return {
            Team.RED.value: 0,
            Team.BLUE.value: 0,
        }
    return {
        Team.RED.value: int(CS.calc_total_score_for_room(Team.RED, room)),
        Team.BLUE.value: int(CS.calc_total_score_for_room(Team.BLUE, room)),
    }


def _pending_payload(room: S.BingoRoomState) -> Dict:
    if not room.is_board_ready():
        return {
            "red": {"xy": None, "hp": None},
            "blue": {"xy": None, "hp": None},
            "max_hp": int(max_hp),
        }
    red_xy = room.get_pending_coord(Team.RED)
    blue_xy = room.get_pending_coord(Team.BLUE)

    def pack(team: Team, xy):
        if xy is None:
            return {"xy": None, "hp": None}
        hp_val = room.get_hp(team)
        return {
            "xy": [xy[0], xy[1]],
            "hp": None if hp_val is None else int(hp_val),
        }

    return {
        "red": pack(Team.RED, red_xy),
        "blue": pack(Team.BLUE, blue_xy),
        "max_hp": int(max_hp),
    }


def _cooldown_payload(room: S.BingoRoomState) -> Dict[str, int]:
    return {
        Team.RED.value: int(room.get_cooldown_remaining(Team.RED)),
        Team.BLUE.value: int(room.get_cooldown_remaining(Team.BLUE)),
    }


def _state_payload(room: S.BingoRoomState, client_team: str) -> Dict:
    joined = {
        Team.RED.value: bool(room.joined_teams.get(Team.RED, False)),
        Team.BLUE.value: bool(room.joined_teams.get(Team.BLUE, False)),
    }
    player_bans = {
        Team.RED.value: list(room.player_bans.get(Team.RED, [])),
        Team.BLUE.value: list(room.player_bans.get(Team.BLUE, [])),
    }
    viewer_bans = []
    if client_team in (Team.RED.value, Team.BLUE.value):
        viewer_bans = list(player_bans.get(client_team, []))
    return {
        "N": room.size,
        "mode": room.mode,
        "pool": room.pool,
        "card": _card_payload(room) if room.is_board_ready() else [],
        "cells": _cells_payload(room) if room.is_board_ready() else {
            Team.RED.value: [],
            Team.BLUE.value: [],
        },
        "sys": {"team": client_team, "op": "toggle_pending"},
        "colors": {
            "red": color_mapping[Team.RED],
            "blue": color_mapping[Team.BLUE],
            "both": color_mapping["both"],
        },
        "scores": _scores_payload(room),
        "pending": _pending_payload(room),
        "cooldown": _cooldown_payload(room),
        "show_reset_button": show_reset_button,
        "team": client_team,
        "phase": "ready" if room.is_ready() else "waiting",
        "ready": room.is_ready(),
        "board_ready": room.is_board_ready(),
        "joined_teams": joined,
        "player_bans": player_bans,
        "viewer_bans": viewer_bans,
        "banned_series_union": room.get_banned_series_union(),
        "available_series": room.get_available_series_ids(),
        "eligible_spellcard_count": room.eligible_spellcard_count(),
        "max_banned_works_per_player": int(max_banned_works_per_player),
    }


def _clear_pending_for_team(room: S.BingoRoomState, team: Team) -> None:
    d = room.team_cell_state_dict[team]
    for k, v in list(d.items()):
        if v == CellState.PENDING:
            room.set_cell_state(team, k, CellState.UNCHECKED)


def _other_team(team: Team) -> Team:
    return Team.BLUE if team == Team.RED else Team.RED


def _apply_click(room: S.BingoRoomState, team: Team, r: int, c: int) -> None:
    xy: Tuple[int, int] = (r, c)
    cur = room.get_cell_state(team, xy)
    if cur == CellState.PENDING:
        if room.mode == "exclusive" and room.get_cooldown_remaining(team) > 0:
            # In exclusive mode, cooldown blocks completion but not selection.
            return
        room.set_cell_state(team, xy, CellState.CHECKED)
        _clear_pending_for_team(room, team)
        room.start_cooldown(team)
        if room.mode == "exclusive":
            other = _other_team(team)
            if room.get_cell_state(other, xy) == CellState.PENDING:
                room.set_cell_state(other, xy, CellState.UNCHECKED)
    elif cur == CellState.CHECKED:
        room.set_cell_state(team, xy, CellState.UNCHECKED)
        room.reset_cooldown(team)
    else:
        if room.mode == "exclusive":
            other = _other_team(team)
            if room.get_cell_state(other, xy) == CellState.CHECKED:
                return
        _clear_pending_for_team(room, team)
        room.set_cell_state(team, xy, CellState.PENDING)


# --- Routes ---

@app.route("/lobby")
def lobby():
    static_dir = app.static_folder or os.path.join(os.path.dirname(__file__), "static")
    return send_from_directory(static_dir, "lobby.html")


@app.route("/api/config")
def api_config():
    """Return server mode and size for lobby display."""
    mode, size, pool = S.get_server_config()
    works_by_pool = {}
    for pool_key in sorted(SPELLCARD_POOLS.keys()):
        try:
            works_by_pool[pool_key] = S.get_pool_series_ids(pool_key)
        except Exception:
            works_by_pool[pool_key] = []
    return jsonify({
        "mode": mode,
        "size": size,
        "pool": pool,
        "pools": sorted(SPELLCARD_POOLS.keys()),
        "works_by_pool": works_by_pool,
        "max_banned_works_per_player": int(max_banned_works_per_player),
    })


def _incompat_response(exc: S.RoomIncompatibleError) -> tuple:
    mode, size, pool = S.get_server_config()
    return jsonify({
        "ok": False,
        "error": "Room incompatible",
        "incompatible": True,
        "message": (
            f"This room was created with mode={exc.room_mode}, size={exc.room_size}, pool={exc.room_pool}. "
            f"Current server settings: mode={mode}, size={size}, pool={pool}. "
            "Please use a new Room ID."
        ),
        "room_mode": exc.room_mode,
        "room_size": exc.room_size,
        "room_pool": exc.room_pool,
        "server_mode": mode,
        "server_size": size,
        "server_pool": pool,
    }), 400


@app.route("/api/lobby/join", methods=["POST"])
def api_lobby_join():
    data = request.get_json(silent=True) or {}
    room_id = (data.get("room") or "").strip()
    team_str = (data.get("team") or "").lower()
    create_mode = (data.get("mode") or "").lower().strip() or None
    create_pool = (data.get("pool") or "").lower().strip() or None
    banned_series = data.get("banned_series") or []
    if not room_id:
        return jsonify({"error": "Room ID required"}), 400
    if team_str not in VALID_CLIENT_TEAMS:
        return jsonify({"error": "Team must be red, blue, or observer"}), 400
    if create_pool is not None and create_pool not in SPELLCARD_POOLS:
        return jsonify({"error": f"Pool must be one of: {', '.join(sorted(SPELLCARD_POOLS.keys()))}"}), 400
    if team_str == "observer" and banned_series:
        return jsonify({"error": "Observer cannot ban works"}), 400
    try:
        room = S.get_room(room_id, create_mode=create_mode, create_pool=create_pool)
    except S.RoomIncompatibleError as e:
        return _incompat_response(e)
    try:
        with room.lock:
            if team_str in (Team.RED.value, Team.BLUE.value):
                room.confirm_team(_enum_from_str_team(team_str), banned_series)
                S.save_room(room)
    except S.RoomBanError as e:
        return jsonify({"error": str(e)}), 400
    broadcast(room_id, "state_updated")
    return jsonify({
        "ok": True,
        "room": room_id,
        "team": team_str,
        "mode": room.mode,
        "pool": room.pool,
        "ready": room.is_ready(),
        "phase": "ready" if room.is_ready() else "waiting",
        "joined_teams": {
            Team.RED.value: bool(room.joined_teams.get(Team.RED, False)),
            Team.BLUE.value: bool(room.joined_teams.get(Team.BLUE, False)),
        },
        "banned_series_union": room.get_banned_series_union(),
    })


@app.route("/")
def index():
    room_id = request.args.get("room")
    team_str = request.args.get("team")
    if not room_id or not team_str:
        return redirect("/lobby")
    if team_str.lower() not in VALID_CLIENT_TEAMS:
        return redirect("/lobby")
    static_dir = app.static_folder or os.path.join(os.path.dirname(__file__), "static")
    return send_from_directory(static_dir, "index.html")


@app.route("/state")
def api_state():
    room_id = request.args.get("room")
    team_str = request.args.get("team")
    if not room_id or not team_str:
        return jsonify({"error": "Missing room or team"}), 400
    try:
        client_team = _normalize_client_team(team_str)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    try:
        room = S.get_room(room_id)
    except S.RoomIncompatibleError as e:
        return _incompat_response(e)
    return jsonify(_state_payload(room, client_team))


@app.route("/click", methods=["POST"])
def api_click():
    room_id = request.args.get("room")
    team_str = request.args.get("team")
    if not room_id or not team_str:
        return jsonify({"error": "Missing room or team"}), 400
    try:
        client_team = _normalize_client_team(team_str)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    if client_team == "observer":
        return jsonify({"error": "Observer cannot click"}), 403
    team = _enum_from_str_team(client_team)

    data = request.get_json(force=True) or {}
    r_raw = data.get("r")
    c_raw = data.get("c")
    if r_raw is None or c_raw is None:
        return jsonify({"error": "Missing r/c"}), 400
    try:
        r, c = int(r_raw), int(c_raw)
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid r/c"}), 400
    try:
        room = S.get_room(room_id)
    except S.RoomIncompatibleError as e:
        return _incompat_response(e)
    if not room.is_ready():
        return jsonify({"error": "Room is waiting for both teams to join"}), 409
    if not (0 <= r < room.size and 0 <= c < room.size):
        return jsonify({"error": "Out of range"}), 400
    with room.lock:
        _apply_click(room, team, r, c)
        S.save_room(room)
    broadcast(room_id, "state_updated")
    return jsonify(_state_payload(room, team.value))


@app.route("/hp", methods=["POST"])
def api_hp():
    room_id = request.args.get("room")
    team_str = request.args.get("team")
    if not room_id or not team_str:
        return jsonify({"error": "Missing room or team"}), 400
    try:
        client_team = _normalize_client_team(team_str)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    if client_team == "observer":
        return jsonify({"error": "Observer cannot adjust HP"}), 403
    team = _enum_from_str_team(client_team)

    data = request.get_json(force=True) or {}
    delta = data.get("delta", 0)
    try:
        delta = int(delta)
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid delta"}), 400

    try:
        room = S.get_room(room_id)
    except S.RoomIncompatibleError as e:
        return _incompat_response(e)
    if not room.is_ready():
        return jsonify({"error": "Room is waiting for both teams to join"}), 409
    xy = room.get_pending_coord(team)
    if xy is None:
        return jsonify({"error": "No pending cell for team"}), 400

    with room.lock:
        room.inc_hp(team, delta)
        S.save_room(room)
    broadcast(room_id, "state_updated")
    return jsonify(_state_payload(room, team.value))


@app.route("/reset", methods=["POST"])
def api_reset():
    if not show_reset_button:
        return jsonify({"error": "Reset button disabled"}), 403

    room_id = request.args.get("room")
    team_str = request.args.get("team")
    if not room_id:
        return jsonify({"error": "Missing room"}), 400
    if not team_str:
        return jsonify({"error": "Missing team"}), 400
    try:
        client_team = _normalize_client_team(team_str)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    if client_team == "observer":
        return jsonify({"error": "Observer cannot reset"}), 403

    try:
        room = S.get_room(room_id)
    except S.RoomIncompatibleError as e:
        return _incompat_response(e)
    if not room.is_ready():
        return jsonify({"error": "Room is waiting for both teams to join"}), 409
    with room.lock:
        room.reset()
        S.save_room(room)
    broadcast(room_id, "state_updated")
    return jsonify(_state_payload(room, Team.RED.value))


@app.route("/events/<room_id>")
def events(room_id: str):
    q: queue.Queue = queue.Queue()
    event_queues.setdefault(room_id, []).append(q)
    return Response(event_stream(q), mimetype="text/event-stream")


def is_serving_process(app) -> bool:
    return (os.environ.get("WERKZEUG_RUN_MAIN") == "true") or (not app.debug)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Spellcard Bingo server")
    parser.add_argument(
        "--mode",
        choices=["shared", "exclusive"],
        default="shared",
        help="Game mode: shared (both teams can complete same cell) or exclusive (first-to-complete wins)",
    )
    parser.add_argument(
        "--size",
        type=int,
        default=5,
        metavar="N",
        help="Grid size (NxN). Default: 5",
    )
    parser.add_argument(
        "--pool",
        choices=sorted(SPELLCARD_POOLS.keys()),
        default=DEFAULT_SPELLCARD_POOL,
        help="Default spellcard pool key for new rooms.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5000,
        help="Port to listen on. Default: 5000",
    )
    args = parser.parse_args()
    S.set_server_config(args.mode, args.size, args.pool)
    S.load_spellcard_data()
    app.run(debug=True, host="0.0.0.0", port=args.port)
