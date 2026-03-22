from defs import (
  target_spellcard_data_path, target_checkpoint_path, 
  CellStateDict, CellState, Team, Coord, OpType,
  N, max_hp, privileged_spellcard_ids
)
import pandas as pd
import pickle
import os
from typing import Dict, List, Optional

# global state var
## in state_dict
team_cell_state_dict: Dict[Team, CellStateDict] = {}
team_hp_dict: Dict[Team, Dict[Coord, int]] = {}
spellcard_id_map: Dict[Coord, int] = {}

## always read afresh
spellcard_data: pd.DataFrame = pd.DataFrame()

## always calculated
spellcard_score_map: Dict[Coord, int] = {}

## always reset
sys_op: OpType = OpType.TOGGLE_PENDING
sys_team: Team = Team.RED

# checkpoint
max_checkpoint_id = 1000
def try_load_latest_checkpoint():
  print(">> Attempting to load latest checkpoint...")
  for id in range(max_checkpoint_id, 0, -1):
    path = target_checkpoint_path.format(id=id)
    try:
      load_checkpoint(path)
      print("<< Checkpoint loaded from", path)
      return True
    except FileNotFoundError:
      continue
  print("<< No checkpoint found, starting fresh.")
  return False
    
def try_save_latest_checkpoint():
  print(">> Attempting to save latest checkpoint...")
  for id in range(max_checkpoint_id, 0, -1):
    path = target_checkpoint_path.format(id=id - 1)
    if os.path.exists(path) or id == 1:
      path = target_checkpoint_path.format(id=id)
      save_checkpoint(path)
      print("<< Checkpoint saved to", path)
      return
  print("<< Warning: No valid checkpoint slot found.")

def save_checkpoint(path):
    
  state_dict = {
    "team_cell_state_dict": team_cell_state_dict,
    "team_hp_dict": team_hp_dict,
    "spellcard_id_map": spellcard_id_map
  }
  pickle.dump(state_dict, open(path, "wb"))

def load_checkpoint(path):
  global team_cell_state_dict, team_cell_state_dict, team_hp_dict, spellcard_id_map
  data = pickle.load(open(path, "rb"))
  try:
    team_cell_state_dict = data.get("team_cell_state_dict")
    team_hp_dict = data.get("team_hp_dict")
    spellcard_id_map = data.get("spellcard_id_map")
  except KeyError as e:
    print(f"Corrupted checkpoint {path}: {e}")

# Initialization
def init_state(reset: bool = False):
  print(">> init state")
  try:
    load_spellcard_data()
  except Exception as e:
    print(f"Error loading spellcard data\n what: \n{e}")
    raise e
  
  if not reset and try_load_latest_checkpoint():
    pass
  else:
    init_team_cell_state_dict()
    init_team_hp_dict()
    # if len(spellcard_id_map) == 0:
    #   sample_spellcard() # init_spellcard_id_map
    
    # always resample spellcards on reset
    sample_spellcard() # init_spellcard_id_map
    
  init_spellcard_score_map()
    
  # print spellcard_id_map
  print("Spellcard sample results:")
  for i in range(N):
    print(" | ", end="")
    for j in range(N):
      print(f"{spellcard_id_map[(i,j)]:3d} ", end="")
    print("|")
  print("<< init state")
  
  


def load_spellcard_data():
  df = pd.read_csv(target_spellcard_data_path)
  
  # drop Placeholder 1~6 columns
  for i in range(1, 7):
    placeholder_col = f"Placeholder{i}"
    if placeholder_col in df.columns:
      df = df.drop(columns=[placeholder_col])
      
  # drop where score is NaN, and warn if any
  df['Score'] = pd.to_numeric(df['Score'], errors='coerce')
  if df['Score'].isnull().any():
    invalid_rows = df[df['Score'].isnull()]
    print("================================================================")
    print(f"Warning: The following {len(invalid_rows)} rows have NaN Score and will be dropped:")
    print(invalid_rows[['SeriesID', 'LocalID', 'SpellcardName']].head(10))
    print("......")
    print("================================================================")
    df = df.dropna(subset=['Score'])
    
  # fill comment nan to ''
  df['Comment'] = df['Comment'].fillna('')
  
  # if LocalID is NaN, replace to 0
  df['LocalID'] = df['LocalID'].fillna(0)

  # Cast IDs to int
  # for col in ['LocalID', 'GlobalID']:
  for col in ['GlobalID']:
    df[col] = pd.to_numeric(df[col], errors='coerce')

  # format 'CanonicalID' to "{SeriesID}-{LocalID}"
  # if LocalID is 0, format it to "{SeriesID}-NonSpell" or "{SeriesID}-NS"
  # Note: some LocalID is now 6A/6B, indicating the stage, so use str instead. NS is deprecated.
  df['CanonicalID'] = df.apply(
    lambda row: f"{row['SeriesID']}-{row['LocalID']}" 
                if row['LocalID'] != 0 else 
                f"{row['SeriesID']}-ns",
    axis=1
  )
  
  global spellcard_data
  spellcard_data = df

def init_team_cell_state_dict():
  global team_cell_state_dict
  for team in [Team.RED, Team.BLUE]:
    team_cell_state_dict[team] = {
      (i, j): CellState.UNCHECKED for i in range(N) for j in range(N)
    }
    
def init_team_hp_dict():
  global team_hp_dict
  for team in [Team.RED, Team.BLUE]:
    team_hp_dict[team] = {
      (i, j): max_hp for i in range(N) for j in range(N)
    }

def sample_spellcard():
  global spellcard_id_map
  # sample NxN unique int from len(spellcard_data)
  total_spellcards = len(spellcard_data)
  import random
  sampled_indices = random.sample(range(total_spellcards), N * N)
  sampled_indices = inject_privileged_spellcard(
    sampled_indices,
    privileged_spellcard_ids
  )
  spellcard_id_map = {
    (i, j): sampled_indices[i * N + j] for i in range(N) for j in range(N)
  }
  
def inject_privileged_spellcard(sampled_indices: List[int], privileged_spellcard_ids: List[int]):  
  import random
  positions = random.sample(range(N * N), len(privileged_spellcard_ids))
  to_evict = [sampled_indices[pos] for pos in positions]
  
  for pos, sc_global_id in zip(positions, privileged_spellcard_ids):
    # seek by GlobalID in spellcard_data
    sc_ids = spellcard_data.index[spellcard_data['GlobalID'] == sc_global_id].tolist()
    if len(sc_ids) != 1:
      raise RuntimeError(f"privileged spellcard with global id {sc_global_id} not found or not unique. len={len(sc_ids)}")
    
    sc_id = sc_ids[0]
    if sc_id not in sampled_indices or \
       sc_id in to_evict:
      sampled_indices[pos] = sc_id
  return sampled_indices


def init_spellcard_score_map():
  global spellcard_score_map
  spellcard_score_map = {
    xy: spellcard_data.iloc[sc_id]['Score']
    for xy, sc_id in spellcard_id_map.items()
  }
  
  
# Access Interface
def get_spellcard(xy: Coord):
  sc_id = spellcard_id_map.get(xy)
  sc_data = spellcard_data[sc_id]
  
  return {
    "name": sc_data['SpellcardName'],
    "score": sc_data['Score'],
    "index": sc_data['CanonicalID'],
    "comment": sc_data['Comment']
  }
  
def get_cell_state(team: Team, xy: Coord) -> CellState:
  return team_cell_state_dict[team][xy]

def set_cell_state(team: Team, xy: Coord, state: CellState):
  team_cell_state_dict[team][xy] = state

def get_cell_hp(team: Team, xy: Coord) -> int:
  return team_hp_dict[team][xy]

def inc_cell_hp(team: Team, xy: Coord, delta: int):
  team_hp_dict[team][xy] += delta
  if team_hp_dict[team][xy] > max_hp:
    team_hp_dict[team][xy] = max_hp
  if team_hp_dict[team][xy] < 0:
    team_hp_dict[team][xy] = 0

def get_pending_coord(team: Team) -> Optional[Coord]:
  for xy, state in team_cell_state_dict[team].items():
    if state == CellState.PENDING:
      return xy
  return None

def get_hp(team: Team) -> int:
  xy = get_pending_coord(team)
  if xy is None:
    return max_hp
  return get_cell_hp(team, xy)

def inc_hp(team: Team, delta: int):
  xy = get_pending_coord(team)
  if xy is None:
    return
  inc_cell_hp(team, xy, delta)

if __name__ == "__main__":
  init_state()
  try_save_latest_checkpoint()


# =============================================================================
# Online mode: per-room state (BingoRoomState, get_room, persistence)
# =============================================================================

import json
import threading

_ROOMS_DIR = "data/rooms"
_bingo_rooms: Dict[str, "BingoRoomState"] = {}

# Server config (set by app.py from CLI)
_SERVER_MODE = "shared"
_SERVER_SIZE = 5


def set_server_config(mode: str, size: int) -> None:
    global _SERVER_MODE, _SERVER_SIZE
    _SERVER_MODE = mode
    _SERVER_SIZE = size


def get_server_config() -> tuple:
    return (_SERVER_MODE, _SERVER_SIZE)


class RoomIncompatibleError(Exception):
    """Raised when a room on disk has different mode/size than server config."""

    def __init__(self, room_mode: str, room_size: int):
        self.room_mode = room_mode
        self.room_size = room_size


def _room_coord_key(xy: Coord) -> str:
    return f"{xy[0]},{xy[1]}"


def _room_parse_coord(s: str) -> Coord:
    r, c = s.split(",", 1)
    return (int(r), int(c))


def _room_serialize_cell_state(d: CellStateDict) -> Dict[str, str]:
    return {_room_coord_key(k): v.value for k, v in d.items()}


def _room_deserialize_cell_state(data: Dict[str, str]) -> CellStateDict:
    return {_room_parse_coord(k): CellState(v) for k, v in data.items()}


def _room_serialize_hp(d: Dict[Coord, int]) -> Dict[str, int]:
    return {_room_coord_key(k): v for k, v in d.items()}


def _room_deserialize_hp(data: Dict[str, int]) -> Dict[Coord, int]:
    return {_room_parse_coord(k): v for k, v in data.items()}


def _room_serialize_spellcard_map(m: Dict[Coord, int]) -> Dict[str, int]:
    return {_room_coord_key(k): v for k, v in m.items()}


def _room_deserialize_spellcard_map(data: Dict[str, int]) -> Dict[Coord, int]:
    return {_room_parse_coord(k): int(v) for k, v in data.items()}


class BingoRoomState:
    """Per-room game state: spellcard grid, cell states, HP (online mode)."""

    def __init__(self, room_id: str, seed: int, mode: str = "shared", size: int = 5):
        self.room_id = room_id
        self.seed = seed
        self.mode = mode
        self.size = size
        self.bingo_bonus = 2 * size
        self.lock = threading.Lock()
        self.spellcard_id_map: Dict[Coord, int] = {}
        self.team_cell_state_dict: Dict[Team, CellStateDict] = {}
        self.team_hp_dict: Dict[Team, Dict[Coord, int]] = {}
        self.spellcard_score_map: Dict[Coord, int] = {}

    def init_fresh(self) -> None:
        n = self.size
        for team in [Team.RED, Team.BLUE]:
            self.team_cell_state_dict[team] = {
                (i, j): CellState.UNCHECKED for i in range(n) for j in range(n)
            }
            self.team_hp_dict[team] = {
                (i, j): max_hp for i in range(n) for j in range(n)
            }
        self._sample_spellcard()
        self._init_spellcard_score_map()

    def _sample_spellcard(self) -> None:
        import random
        rng = random.Random(self.seed)
        total = len(spellcard_data)
        n = self.size
        sampled = rng.sample(range(total), n * n)
        sampled = self._inject_privileged(sampled)
        self.spellcard_id_map = {
            (i, j): sampled[i * n + j] for i in range(n) for j in range(n)
        }

    def _inject_privileged(self, sampled: List[int]) -> List[int]:
        import random
        rng = random.Random(self.seed + 1)
        n = self.size
        positions = rng.sample(range(n * n), len(privileged_spellcard_ids))
        to_evict = [sampled[pos] for pos in positions]
        for pos, sc_global_id in zip(positions, privileged_spellcard_ids):
            sc_ids = spellcard_data.index[
                spellcard_data["GlobalID"] == sc_global_id
            ].tolist()
            if len(sc_ids) != 1:
                raise RuntimeError(
                    f"privileged spellcard {sc_global_id} not found or not unique"
                )
            sc_id = sc_ids[0]
            if sc_id not in sampled or sc_id in to_evict:
                sampled[pos] = sc_id
        return sampled

    def _init_spellcard_score_map(self) -> None:
        self.spellcard_score_map = {
            xy: int(spellcard_data.iloc[sc_id]["Score"])
            for xy, sc_id in self.spellcard_id_map.items()
        }

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "size": self.size,
            "spellcard_id_map": _room_serialize_spellcard_map(
                self.spellcard_id_map
            ),
            "team_cell_state_dict": {
                t.value: _room_serialize_cell_state(d)
                for t, d in self.team_cell_state_dict.items()
            },
            "team_hp_dict": {
                t.value: _room_serialize_hp(d)
                for t, d in self.team_hp_dict.items()
            },
        }

    def get_cell_state(self, team: Team, xy: Coord) -> CellState:
        return self.team_cell_state_dict[team][xy]

    def set_cell_state(self, team: Team, xy: Coord, state: CellState) -> None:
        self.team_cell_state_dict[team][xy] = state

    def get_cell_hp(self, team: Team, xy: Coord) -> int:
        return self.team_hp_dict[team][xy]

    def inc_cell_hp(self, team: Team, xy: Coord, delta: int) -> None:
        self.team_hp_dict[team][xy] += delta
        if self.team_hp_dict[team][xy] > max_hp:
            self.team_hp_dict[team][xy] = max_hp
        if self.team_hp_dict[team][xy] < 0:
            self.team_hp_dict[team][xy] = 0

    def get_pending_coord(self, team: Team) -> Optional[Coord]:
        for xy, st in self.team_cell_state_dict[team].items():
            if st == CellState.PENDING:
                return xy
        return None

    def get_hp(self, team: Team) -> int:
        xy = self.get_pending_coord(team)
        if xy is None:
            return max_hp
        return self.get_cell_hp(team, xy)

    def inc_hp(self, team: Team, delta: int) -> None:
        xy = self.get_pending_coord(team)
        if xy is None:
            return
        self.inc_cell_hp(team, xy, delta)

    def get_spellcard(self, xy: Coord) -> dict:
        sc_id = self.spellcard_id_map.get(xy)
        if sc_id is None:
            return {"name": "", "score": 0, "index": "", "comment": ""}
        rec = spellcard_data.iloc[int(sc_id)]
        return {
            "name": str(rec.get("SpellcardName", "")),
            "score": int(rec.get("Score", 0)),
            "index": str(rec.get("CanonicalID", "")),
            "comment": str(rec.get("Comment", "")),
        }

    def reset(self) -> None:
        self.init_fresh()

    @classmethod
    def from_dict(cls, room_id: str, data: dict) -> "BingoRoomState":
        seed = sum(ord(c) for c in room_id)
        mode = data.get("mode", "shared")
        size = data.get("size")
        if size is None:
            sm = data.get("spellcard_id_map", {})
            if sm:
                max_coord = max(
                    (int(s.split(",")[0]), int(s.split(",")[1])) for s in sm
                )
                size = max(max_coord[0], max_coord[1]) + 1
            else:
                size = 5
        obj = cls(room_id, seed, mode=mode, size=int(size))
        obj.spellcard_id_map = _room_deserialize_spellcard_map(
            data.get("spellcard_id_map", {})
        )
        obj.team_cell_state_dict = {
            Team(t): _room_deserialize_cell_state(d)
            for t, d in data.get("team_cell_state_dict", {}).items()
        }
        obj.team_hp_dict = {
            Team(t): _room_deserialize_hp(d)
            for t, d in data.get("team_hp_dict", {}).items()
        }
        obj._init_spellcard_score_map()
        return obj


def _room_state_path(room_id: str) -> str:
    safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in room_id)
    return os.path.join(_ROOMS_DIR, safe_id, "state.json")


def _load_room_from_disk(room_id: str) -> Optional[BingoRoomState]:
    path = _room_state_path(room_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return BingoRoomState.from_dict(room_id, data)
    except Exception as e:
        print(f"[state] Failed to load room {path}: {e}")
        return None


def _save_room_to_disk(room: BingoRoomState) -> None:
    path = _room_state_path(room.room_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(room.to_dict(), f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[state] Failed to save room {path}: {e}")


def ensure_spellcard_data_loaded() -> None:
    """Ensure global spellcard data is loaded (call before get_room)."""
    if spellcard_data is None or len(spellcard_data) == 0:
        load_spellcard_data()


def get_room(room_id: str, create_mode: Optional[str] = None) -> BingoRoomState:
    """Get or create room; load from disk if present (online mode).
    create_mode: mode for new rooms (used when room does not exist). Default: server mode.
    Raises RoomIncompatibleError if room on disk has different size than server."""
    ensure_spellcard_data_loaded()
    if room_id in _bingo_rooms:
        return _bingo_rooms[room_id]
    loaded = _load_room_from_disk(room_id)
    if loaded is not None:
        if loaded.size != _SERVER_SIZE:
            raise RoomIncompatibleError(loaded.mode, loaded.size)
        _bingo_rooms[room_id] = loaded
        return loaded
    seed = sum(ord(c) for c in room_id)
    mode = create_mode if create_mode in ("shared", "exclusive") else _SERVER_MODE
    room = BingoRoomState(room_id, seed, mode=mode, size=_SERVER_SIZE)
    room.init_fresh()
    _bingo_rooms[room_id] = room
    _save_room_to_disk(room)
    return room


def save_room(room: BingoRoomState) -> None:
    """Persist room state to disk (online mode)."""
    _save_room_to_disk(room)