import state as S
from defs import *

from typing import List, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from state import BingoRoomState

def line_score(line_values: List[int], bingo_bonus_val: int = None) -> int:
  # return sum(line_values) # modify this line to change scoring rule
  return bingo_bonus_val if bingo_bonus_val is not None else bingo_bonus


def check_valid_line(line_type: LineType, index: int, n: int = None) -> bool:
  size = n if n is not None else N
  if line_type == LineType.ROW or line_type == LineType.COLUMN:
    return 0 <= index < size
  if line_type == LineType.DIAGONAL:
    return index in (0, 1)
  raise RuntimeError(f"Invalid line type {line_type} {index}, N={size}")


def get_line_values(dict: Dict[Coord, Any], line_type: LineType, index: int, n: int = None) -> List[Any]:
  size = n if n is not None else N
  check_valid_line(line_type, index, size)

  values = []
  if line_type == LineType.ROW:
    for col in range(size):
      values.append(dict.get((index, col)))
    return values
  if line_type == LineType.COLUMN:
    for row in range(size):
      values.append(dict.get((row, index)))
    return values
  if line_type == LineType.DIAGONAL:
    if index == 0:
      for i in range(size):
        values.append(dict.get((i, i)))
      return values
    else:
      for i in range(size):
        values.append(dict.get((i, size - 1 - i)))
      return values

def check_bingo(team: Team, line_type: LineType, index: int) -> bool:
  cell_state_dict = S.team_cell_state_dict[team]
  line_values = get_line_values(cell_state_dict, line_type, index)
  return all(state == CellState.CHECKED for state in line_values)

def calc_bingo_scores(line_type: LineType, index: int) -> int:
  score_dict = S.spellcard_score_map
  line_values = get_line_values(score_dict, line_type, index)
  return line_score(line_values)


def calc_total_bingo_scores(team: Team) -> int:
  total_score = 0
  for i in range(N):
    if check_bingo(team, LineType.ROW, i):
      total_score += calc_bingo_scores(LineType.ROW, i)
    if check_bingo(team, LineType.COLUMN, i):
      total_score += calc_bingo_scores(LineType.COLUMN, i)
  for i in range(2):
    if check_bingo(team, LineType.DIAGONAL, i):
      total_score += calc_bingo_scores(LineType.DIAGONAL, i)
  return total_score

def calc_total_score(team: Team) -> int:
  cell_state_dict = S.team_cell_state_dict[team]
  score_dict = S.spellcard_score_map
  
  total_checked_score = 0
  for coord, state in cell_state_dict.items():
    if state == CellState.CHECKED:
      total_checked_score += score_dict.get(coord, 0)

  total_bingo_score = calc_total_bingo_scores(team)

  return total_checked_score + total_bingo_score


# Room-aware scoring (for online mode)
def calc_total_score_for_room(team: Team, room: "BingoRoomState") -> int:
  """Compute total score for a team using per-room state."""
  cell_state_dict = room.team_cell_state_dict[team]
  score_dict = room.spellcard_score_map

  total_checked_score = 0
  for coord, state in cell_state_dict.items():
    if state == CellState.CHECKED:
      total_checked_score += score_dict.get(coord, 0)

  total_bingo_score = calc_total_bingo_scores_for_room(team, room)
  return total_checked_score + total_bingo_score


def check_bingo_for_room(team: Team, line_type: LineType, index: int, room: "BingoRoomState") -> bool:
  cell_state_dict = room.team_cell_state_dict[team]
  line_values = get_line_values(cell_state_dict, line_type, index, room.size)
  return all(state == CellState.CHECKED for state in line_values)


def calc_bingo_scores_for_room(line_type: LineType, index: int, room: "BingoRoomState") -> int:
  score_dict = room.spellcard_score_map
  line_values = get_line_values(score_dict, line_type, index, room.size)
  return line_score(line_values, room.bingo_bonus)


def calc_total_bingo_scores_for_room(team: Team, room: "BingoRoomState") -> int:
  total_score = 0
  n = room.size
  for i in range(n):
    if check_bingo_for_room(team, LineType.ROW, i, room):
      total_score += calc_bingo_scores_for_room(LineType.ROW, i, room)
    if check_bingo_for_room(team, LineType.COLUMN, i, room):
      total_score += calc_bingo_scores_for_room(LineType.COLUMN, i, room)
  for i in (0, 1):
    if check_bingo_for_room(team, LineType.DIAGONAL, i, room):
      total_score += calc_bingo_scores_for_room(LineType.DIAGONAL, i, room)
  return total_score