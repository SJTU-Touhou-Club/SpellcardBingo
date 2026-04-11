from enum import Enum
from typing import Dict, List, Tuple, Union

N = 6

class Team(Enum):
  RED = "red"
  BLUE = "blue"
  
color_mapping: Dict[Union[Team, str], str] = {
  Team.RED: "#EE5755",
  Team.BLUE: "#5557EE",
  "both": "#E000E0",
}

class CellState(Enum):
  CHECKED = "checked"
  UNCHECKED = "unchecked"
  PENDING = "pending"

class LineType(Enum):
  ROW = "row"
  COLUMN = "column"
  DIAGONAL = "diagonal"
  
class OpType(Enum):
  TOGGLE_CHECK = "toggle_check"
  TOGGLE_PENDING = "toggle_pending"

Coord = Tuple[int, int]  # (row, col)
CellStateDict = Dict[Coord, CellState]  # Mapping from (row, col) to CellState

# Global Constant
max_hp = 5 # initial challenge times for each spell card

# Spellcard CSV pools (key -> path). Online rooms pick one pool per room.
SPELLCARD_POOLS: Dict[str, str] = {
  "normal": "data/SpellcardDataNormal.csv",
  "lunatic": "data/SpellcardDataLunatic.csv",
}
DEFAULT_SPELLCARD_POOL = "normal"

# Per-pool GlobalIDs for always-sampled spellcards (empty list skips injection for that pool)
privileged_spellcard_ids: Dict[str, List[int]] = {
  "normal": [364],  # 弑神炮麻将山
  "lunatic": [],
}

# Per-player maximum number of works (`SeriesID`) that may be banned before room start.
max_banned_works_per_player = 2

# Legacy single path: default pool (local checkpoint / load_spellcard_data default)
target_spellcard_data_path = SPELLCARD_POOLS[DEFAULT_SPELLCARD_POOL]

# Bingo Scoring Rules
bingo_bonus = 10
# Cooldown (seconds) after completion in exclusive mode
exclusive_mode_cooldown = 30

target_checkpoint_path = "data/checkpoint-{id}.pickle"

# Show Reset Button
show_reset_button = False
