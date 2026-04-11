from defs import (
  target_checkpoint_path,
  SPELLCARD_POOLS,
  DEFAULT_SPELLCARD_POOL,
  CellStateDict,
  CellState,
  Team,
  Coord,
  OpType,
  N,
  max_hp,
  privileged_spellcard_ids,
  exclusive_mode_cooldown,
  max_banned_works_per_player,
)
import pandas as pd
import pickle
import os
import time
from typing import Dict, List, Optional

# global state var
## in state_dict
team_cell_state_dict: Dict[Team, CellStateDict] = {}
team_hp_dict: Dict[Team, Dict[Coord, int]] = {}
spellcard_id_map: Dict[Coord, int] = {}

## always read afresh (default pool; offline mode)
spellcard_data: pd.DataFrame = pd.DataFrame()
## all pools for online rooms (key -> DataFrame)
spellcard_data_by_pool: Dict[str, pd.DataFrame] = {}

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
  
  


SPELLCARD_DATA_COLUMNS = [
  "GlobalID", "SeriesID", "LocalID", "SpellcardName", "Score", "Comment",
]


def _parse_spellcard_csv(path: str) -> pd.DataFrame:
  df = pd.read_csv(path)
  missing = [c for c in SPELLCARD_DATA_COLUMNS if c not in df.columns]
  if missing:
    raise ValueError(
      f"Spellcard CSV {path} missing required columns {missing}; "
      f"expected exactly: {SPELLCARD_DATA_COLUMNS}"
    )
  df = df[SPELLCARD_DATA_COLUMNS].copy()

  df["Score"] = pd.to_numeric(df["Score"], errors="coerce")
  if df["Score"].isnull().any():
    invalid_rows = df[df["Score"].isnull()]
    print("================================================================")
    print(
      f"Warning: The following {len(invalid_rows)} rows have NaN Score and will be dropped:"
    )
    print(invalid_rows[["SeriesID", "LocalID", "SpellcardName"]].head(10))
    print("......")
    print("================================================================")
    df = df.dropna(subset=["Score"])
  df = df.reset_index(drop=True)

  df["Comment"] = df["Comment"].fillna("")
  df["LocalID"] = df["LocalID"].fillna(0)

  for col in ["GlobalID"]:
    df[col] = pd.to_numeric(df[col], errors="coerce")

  df["CanonicalID"] = df.apply(
    lambda row: f"{row['SeriesID']}-{row['LocalID']}"
    if row["LocalID"] != 0
    else f"{row['SeriesID']}-ns",
    axis=1,
  )
  return df


def load_all_spellcard_pools() -> None:
  global spellcard_data_by_pool
  spellcard_data_by_pool = {}
  for pool_key, path in SPELLCARD_POOLS.items():
    spellcard_data_by_pool[pool_key] = _parse_spellcard_csv(path)


def get_spellcard_df(pool: str) -> pd.DataFrame:
  if pool not in spellcard_data_by_pool:
    raise KeyError(f"unknown spellcard pool {pool!r}")
  return spellcard_data_by_pool[pool]


def get_pool_series_ids(pool: str) -> List[str]:
  df = get_spellcard_df(pool)
  vals: List[str] = []
  seen = set()
  for raw in df["SeriesID"].tolist():
    key = str(raw or "").strip()
    if not key or key in seen:
      continue
    seen.add(key)
    vals.append(key)
  return vals


def load_spellcard_data():
  """Load every pool; set global `spellcard_data` to the default pool (offline mode)."""
  load_all_spellcard_pools()
  global spellcard_data
  spellcard_data = spellcard_data_by_pool[DEFAULT_SPELLCARD_POOL]

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
    privileged_spellcard_ids.get(DEFAULT_SPELLCARD_POOL, []),
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
_SERVER_POOL = DEFAULT_SPELLCARD_POOL


def set_server_config(mode: str, size: int, pool: str = DEFAULT_SPELLCARD_POOL) -> None:
    global _SERVER_MODE, _SERVER_SIZE, _SERVER_POOL
    _SERVER_MODE = mode
    _SERVER_SIZE = size
    _SERVER_POOL = pool if pool in SPELLCARD_POOLS else DEFAULT_SPELLCARD_POOL


def get_server_config() -> tuple:
    return (_SERVER_MODE, _SERVER_SIZE, _SERVER_POOL)


class RoomIncompatibleError(Exception):
    """Raised when a room on disk has different mode/size/pool than server config."""

    def __init__(self, room_mode: str, room_size: int, room_pool: str):
        self.room_mode = room_mode
        self.room_size = room_size
        self.room_pool = room_pool


class RoomBanError(Exception):
    """Raised when requested room bans are invalid or leave too few eligible cards."""

    pass


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


def _normalize_series_ids(items) -> List[str]:
    if not isinstance(items, list):
        return []
    out: List[str] = []
    seen = set()
    for raw in items:
        val = str(raw or "").strip()
        if not val or val in seen:
            continue
        seen.add(val)
        out.append(val)
    return out


class BingoRoomState:
    """Per-room game state: spellcard grid, cell states, HP (online mode)."""

    def __init__(
        self,
        room_id: str,
        seed: int,
        mode: str = "shared",
        size: int = 5,
        pool: str = DEFAULT_SPELLCARD_POOL,
    ):
        self.room_id = room_id
        self.seed = seed
        self.mode = mode
        self.size = size
        self.pool = pool if pool in SPELLCARD_POOLS else DEFAULT_SPELLCARD_POOL
        self.bingo_bonus = 2 * size
        self.lock = threading.Lock()
        self.spellcard_id_map: Dict[Coord, int] = {}
        self.team_cell_state_dict: Dict[Team, CellStateDict] = {}
        self.team_hp_dict: Dict[Team, Dict[Coord, int]] = {}
        self.spellcard_score_map: Dict[Coord, int] = {}
        self.player_bans: Dict[Team, List[str]] = {
            Team.RED: [],
            Team.BLUE: [],
        }
        self.joined_teams: Dict[Team, bool] = {
            Team.RED: False,
            Team.BLUE: False,
        }
        self.team_cooldown_until: Dict[Team, float] = {
            Team.RED: 0.0,
            Team.BLUE: 0.0,
        }

    def _df(self) -> pd.DataFrame:
        return get_spellcard_df(self.pool)

    def init_fresh(self) -> None:
        n = self.size
        for team in [Team.RED, Team.BLUE]:
            self.team_cell_state_dict[team] = {
                (i, j): CellState.UNCHECKED for i in range(n) for j in range(n)
            }
            self.team_hp_dict[team] = {
                (i, j): max_hp for i in range(n) for j in range(n)
            }
            self.team_cooldown_until[team] = 0.0
        self.spellcard_id_map = {}
        self.spellcard_score_map = {}

    def get_available_series_ids(self) -> List[str]:
        df = self._df()
        vals = []
        seen = set()
        for raw in df["SeriesID"].tolist():
            key = str(raw or "").strip()
            if not key or key in seen:
                continue
            seen.add(key)
            vals.append(key)
        return vals

    def eligible_spellcard_count(self, banned_series: Optional[List[str]] = None) -> int:
        banned = set(banned_series if banned_series is not None else self.get_banned_series_union())
        df = self._df()
        if not banned:
            return int(len(df))
        return int((~df["SeriesID"].astype(str).isin(banned)).sum())

    def get_banned_series_union(self) -> List[str]:
        seen = set()
        out: List[str] = []
        for team in [Team.RED, Team.BLUE]:
            for series_id in self.player_bans.get(team, []):
                if series_id in seen:
                    continue
                seen.add(series_id)
                out.append(series_id)
        return out

    def is_board_ready(self) -> bool:
        return len(self.spellcard_id_map) == self.size * self.size

    def is_ready(self) -> bool:
        return self.joined_teams.get(Team.RED, False) and self.joined_teams.get(Team.BLUE, False) and self.is_board_ready()

    def _eligible_indices(self, banned_series: Optional[List[str]] = None) -> List[int]:
        df = self._df()
        banned = set(banned_series if banned_series is not None else self.get_banned_series_union())
        if not banned:
            return df.index.tolist()
        mask = ~df["SeriesID"].astype(str).isin(banned)
        return df.index[mask].tolist()

    def _sample_spellcard(self, banned_series: Optional[List[str]] = None) -> None:
        import random
        rng = random.Random(self.seed)
        n = self.size
        eligible_indices = self._eligible_indices(banned_series)
        if len(eligible_indices) < n * n:
            raise RoomBanError(
                f"Not enough spellcards remain after bans: need {n * n}, have {len(eligible_indices)}."
            )
        sampled = rng.sample(eligible_indices, n * n)
        sampled = self._inject_privileged(sampled, banned_series=banned_series)
        self.spellcard_id_map = {
            (i, j): sampled[i * n + j] for i in range(n) for j in range(n)
        }

    def _inject_privileged(self, sampled: List[int], banned_series: Optional[List[str]] = None) -> List[int]:
        import random
        rng = random.Random(self.seed + 1)
        n = self.size
        pool_privileged_ids = privileged_spellcard_ids.get(self.pool, [])
        if not pool_privileged_ids:
            return sampled
        positions = rng.sample(range(n * n), len(pool_privileged_ids))
        to_evict = [sampled[pos] for pos in positions]
        df = self._df()
        banned = set(banned_series if banned_series is not None else self.get_banned_series_union())
        for pos, sc_global_id in zip(positions, pool_privileged_ids):
            sc_ids = df.index[
                df["GlobalID"] == sc_global_id
            ].tolist()
            if len(sc_ids) != 1:
                raise RuntimeError(
                    f"privileged spellcard {sc_global_id} not found or not unique"
                )
            sc_id = sc_ids[0]
            series_id = str(df.loc[sc_id, "SeriesID"])
            if series_id in banned:
                continue
            if sc_id not in sampled or sc_id in to_evict:
                sampled[pos] = sc_id
        return sampled

    def _init_spellcard_score_map(self) -> None:
        df = self._df()
        self.spellcard_score_map = {
            xy: int(df.loc[sc_id]["Score"])
            for xy, sc_id in self.spellcard_id_map.items()
        }

    def ensure_board_ready(self) -> None:
        if self.is_board_ready():
            return
        self._sample_spellcard(self.get_banned_series_union())
        self._init_spellcard_score_map()

    def confirm_team(self, team: Team, banned_series: List[str]) -> None:
        normalized = _normalize_series_ids(banned_series)
        if len(normalized) > max_banned_works_per_player:
            raise RoomBanError(
                f"At most {max_banned_works_per_player} banned works are allowed per player."
            )
        allowed_series = set(self.get_available_series_ids())
        unknown = [sid for sid in normalized if sid not in allowed_series]
        if unknown:
            raise RoomBanError(f"Unknown work(s): {', '.join(unknown)}")

        # Validate against the merged room ban set before confirming this player.
        next_bans = {
            Team.RED: list(self.player_bans.get(Team.RED, [])),
            Team.BLUE: list(self.player_bans.get(Team.BLUE, [])),
        }
        next_bans[team] = normalized
        merged = []
        seen = set()
        for series_id in next_bans[Team.RED] + next_bans[Team.BLUE]:
            if series_id in seen:
                continue
            seen.add(series_id)
            merged.append(series_id)
        if self.eligible_spellcard_count(merged) < self.size * self.size:
            raise RoomBanError(
                "These bans leave too few spellcards to generate the board. Please remove some banned works."
            )

        self.player_bans[team] = normalized
        self.joined_teams[team] = True
        if self.joined_teams[Team.RED] and self.joined_teams[Team.BLUE]:
            self.ensure_board_ready()

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "size": self.size,
            "pool": self.pool,
            "player_bans": {
                t.value: list(self.player_bans.get(t, []))
                for t in [Team.RED, Team.BLUE]
            },
            "joined_teams": {
                t.value: bool(self.joined_teams.get(t, False))
                for t in [Team.RED, Team.BLUE]
            },
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
            "team_cooldown_until": {
                t.value: float(self.team_cooldown_until.get(t, 0.0))
                for t in [Team.RED, Team.BLUE]
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
        rec = self._df().loc[int(sc_id)]
        return {
            "name": str(rec.get("SpellcardName", "")),
            "score": int(rec.get("Score", 0)),
            "index": str(rec.get("CanonicalID", "")),
            "comment": str(rec.get("Comment", "")),
        }

    def reset(self) -> None:
        self.init_fresh()
        if self.joined_teams[Team.RED] and self.joined_teams[Team.BLUE]:
            self.ensure_board_ready()

    def get_cooldown_remaining(self, team: Team, now: Optional[float] = None) -> int:
        if self.mode != "exclusive":
            return 0
        ts = now if now is not None else time.time()
        remaining = float(self.team_cooldown_until.get(team, 0.0)) - ts
        if remaining <= 0:
            return 0
        return int(remaining + 0.999999)

    def start_cooldown(self, team: Team, now: Optional[float] = None) -> None:
        if self.mode != "exclusive":
            self.team_cooldown_until[team] = 0.0
            return
        ts = now if now is not None else time.time()
        self.team_cooldown_until[team] = ts + float(exclusive_mode_cooldown)

    def reset_cooldown(self, team: Team) -> None:
        self.team_cooldown_until[team] = 0.0

    @classmethod
    def from_dict(cls, room_id: str, data: dict) -> "BingoRoomState":
        seed = sum(ord(c) for c in room_id)
        mode = data.get("mode", "shared")
        pool = data.get("pool", DEFAULT_SPELLCARD_POOL)
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
        obj = cls(room_id, seed, mode=mode, size=int(size), pool=pool)
        raw_bans = data.get("player_bans", {}) or {}
        obj.player_bans = {
            Team.RED: _normalize_series_ids(raw_bans.get(Team.RED.value, [])),
            Team.BLUE: _normalize_series_ids(raw_bans.get(Team.BLUE.value, [])),
        }
        raw_joined = data.get("joined_teams", {}) or {}
        obj.joined_teams = {
            Team.RED: bool(raw_joined.get(Team.RED.value, False)),
            Team.BLUE: bool(raw_joined.get(Team.BLUE.value, False)),
        }
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
        raw_cd = data.get("team_cooldown_until", {}) or {}
        obj.team_cooldown_until = {
            Team.RED: float(raw_cd.get(Team.RED.value, 0.0) or 0.0),
            Team.BLUE: float(raw_cd.get(Team.BLUE.value, 0.0) or 0.0),
        }
        if obj.spellcard_id_map:
            # Legacy rooms with an already-sampled board should remain playable.
            if not raw_joined:
                obj.joined_teams = {
                    Team.RED: True,
                    Team.BLUE: True,
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
    if not spellcard_data_by_pool:
        load_spellcard_data()


def get_room(
    room_id: str,
    create_mode: Optional[str] = None,
    create_pool: Optional[str] = None,
) -> BingoRoomState:
    """Get or create room; load from disk if present (online mode).
    create_mode: mode for new rooms (used when room does not exist). Default: server mode.
    create_pool: pool key for new rooms (used when room does not exist). Default: server pool.
    Raises RoomIncompatibleError if room on disk has different size/pool than requested."""
    ensure_spellcard_data_loaded()
    requested_pool = create_pool if create_pool in SPELLCARD_POOLS else None
    if room_id in _bingo_rooms:
        cached = _bingo_rooms[room_id]
        if cached.size != _SERVER_SIZE:
            raise RoomIncompatibleError(cached.mode, cached.size, cached.pool)
        if requested_pool is not None and cached.pool != requested_pool:
            raise RoomIncompatibleError(cached.mode, cached.size, cached.pool)
        return cached
    loaded = _load_room_from_disk(room_id)
    if loaded is not None:
        if loaded.size != _SERVER_SIZE:
            raise RoomIncompatibleError(loaded.mode, loaded.size, loaded.pool)
        if requested_pool is not None and loaded.pool != requested_pool:
            raise RoomIncompatibleError(loaded.mode, loaded.size, loaded.pool)
        _bingo_rooms[room_id] = loaded
        return loaded
    seed = sum(ord(c) for c in room_id)
    mode = create_mode if create_mode in ("shared", "exclusive") else _SERVER_MODE
    pool = requested_pool if requested_pool is not None else _SERVER_POOL
    room = BingoRoomState(room_id, seed, mode=mode, size=_SERVER_SIZE, pool=pool)
    room.init_fresh()
    _bingo_rooms[room_id] = room
    _save_room_to_disk(room)
    return room


def save_room(room: BingoRoomState) -> None:
    """Persist room state to disk (online mode)."""
    _save_room_to_disk(room)