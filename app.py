"""Flask server for Spellcard Bingo (online mode).

Endpoints:
- GET  /lobby         -> serve lobby page
- POST /api/lobby/join -> { room, team } -> create/join room, redirect to game
- GET  /              -> require ?room= & ?team=, else redirect to /lobby
- GET  /state         -> ?room= & ?team= -> full state payload
- POST /click         -> ?room= & ?team=, body { r, c } -> apply click for team
- POST /hp            -> ?room= & ?team=, body { team, delta } -> adjust HP
- POST /reset         -> ?room= -> reset room (if allowed)
- GET  /events/<room_id> -> SSE stream for room
"""

import argparse
import queue
import os

from flask import Flask, jsonify, request, send_from_directory, redirect
from flask import Response
from typing import Dict, List, Tuple

from defs import Team, CellState, color_mapping, max_hp, show_reset_button
import state as S
import calc_score as CS

app = Flask(__name__, static_folder="static", static_url_path="")

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


def _card_payload(room: S.BingoRoomState) -> List[List[Dict]]:
    n = room.size
    grid: List[List[Dict]] = []
    for r in range(n):
        row: List[Dict] = []
        for c in range(n):
            sc_id = room.spellcard_id_map.get((r, c))
            rec = (
                S.spellcard_data.iloc[int(sc_id)]
                if sc_id is not None
                else None
            )
            row.append({
                "name": None if rec is None else str(rec.get("SpellcardName", "")),
                "score": 0 if rec is None else int(rec.get("Score", 0)),
                "index": None if rec is None else str(rec.get("CanonicalID", "")),
                "comment": None if rec is None else str(rec.get("Comment", "")),
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
    return {
        Team.RED.value: int(CS.calc_total_score_for_room(Team.RED, room)),
        Team.BLUE.value: int(CS.calc_total_score_for_room(Team.BLUE, room)),
    }


def _pending_payload(room: S.BingoRoomState) -> Dict:
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


def _state_payload(room: S.BingoRoomState, client_team: str) -> Dict:
    return {
        "N": room.size,
        "mode": room.mode,
        "card": _card_payload(room),
        "cells": _cells_payload(room),
        "sys": {"team": client_team, "op": "toggle_pending"},
        "colors": {
            "red": color_mapping[Team.RED],
            "blue": color_mapping[Team.BLUE],
            "both": color_mapping["both"],
        },
        "scores": _scores_payload(room),
        "pending": _pending_payload(room),
        "show_reset_button": show_reset_button,
        "team": client_team,
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
        room.set_cell_state(team, xy, CellState.CHECKED)
        _clear_pending_for_team(room, team)
        if room.mode == "exclusive":
            other = _other_team(team)
            if room.get_cell_state(other, xy) == CellState.PENDING:
                room.set_cell_state(other, xy, CellState.UNCHECKED)
    elif cur == CellState.CHECKED:
        room.set_cell_state(team, xy, CellState.UNCHECKED)
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
    mode, size = S.get_server_config()
    return jsonify({"mode": mode, "size": size})


def _incompat_response(exc: S.RoomIncompatibleError) -> tuple:
    mode, size = S.get_server_config()
    return jsonify({
        "ok": False,
        "error": "Room incompatible",
        "incompatible": True,
        "message": (
            f"This room was created with mode={exc.room_mode}, size={exc.room_size}. "
            f"Current server settings: mode={mode}, size={size}. "
            "Please use a new Room ID."
        ),
        "room_mode": exc.room_mode,
        "room_size": exc.room_size,
        "server_mode": mode,
        "server_size": size,
    }), 400


@app.route("/api/lobby/join", methods=["POST"])
def api_lobby_join():
    data = request.get_json(silent=True) or {}
    room_id = (data.get("room") or "").strip()
    team_str = (data.get("team") or "").lower()
    create_mode = (data.get("mode") or "").lower().strip() or None
    if not room_id:
        return jsonify({"error": "Room ID required"}), 400
    if team_str not in ("red", "blue"):
        return jsonify({"error": "Team must be red or blue"}), 400
    try:
        room = S.get_room(room_id, create_mode=create_mode)
    except S.RoomIncompatibleError as e:
        return _incompat_response(e)
    return jsonify({"ok": True, "room": room_id, "team": team_str, "mode": room.mode})


@app.route("/")
def index():
    room_id = request.args.get("room")
    team_str = request.args.get("team")
    if not room_id or not team_str:
        return redirect("/lobby")
    if team_str.lower() not in ("red", "blue"):
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
        team = _enum_from_str_team(team_str)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    try:
        room = S.get_room(room_id)
    except S.RoomIncompatibleError as e:
        return _incompat_response(e)
    return jsonify(_state_payload(room, team.value))


@app.route("/click", methods=["POST"])
def api_click():
    room_id = request.args.get("room")
    team_str = request.args.get("team")
    if not room_id or not team_str:
        return jsonify({"error": "Missing room or team"}), 400
    try:
        team = _enum_from_str_team(team_str)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

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
        team = _enum_from_str_team(team_str)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

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
    if not room_id:
        return jsonify({"error": "Missing room"}), 400

    try:
        room = S.get_room(room_id)
    except S.RoomIncompatibleError as e:
        return _incompat_response(e)
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
        "--port",
        type=int,
        default=5000,
        help="Port to listen on. Default: 5000",
    )
    args = parser.parse_args()
    S.set_server_config(args.mode, args.size)
    S.load_spellcard_data()
    app.run(debug=True, host="0.0.0.0", port=args.port)
