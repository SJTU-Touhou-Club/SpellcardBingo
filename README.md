# Spellcard Bingo!

This repository contains the UI for the Spellcard Bingo game used at the SJTU Touhou Festival 2025.

---

## Credits

- This project is inspired by [th-bingo](https://github.com/CuteReimu/th-bingo).

- 落星, 带鸽子 @ SJTU
	- Project proposal
	- Spellcard data collection and scoring for NORMAL pool
- fAKe @ SJTU
	- Core code design and implement.
- Copilot 様 
	- GPT-5@OpenAI, Gemini 3.0 Pro@Google, and Cursor
	- Frontend coding and refinement.

> You're welcome to adapt this project for your Touhou events. Please credit us as “上海交通大学东方社”.

> You don't need our prior permission to use it, though we'd love to hear about your usage.

---

## Contact

1. For technical questions (improvements, deployment issues, etc.), email to [fake@sjtu.edu.cn](mailto:fake@sjtu.edu.cn), or open an issue/pull request in this repository.

2. If you adapt this project for your own Touhou event, feel free to let us know by contacting the administrators in any of our club's QQ groups (e.g., `471319153` for vistors).

---

# Manual

---

## Game Rules

Two teams compete to gain higher scores, where each team member can challenge a limited number of spellcards.

**Game modes:**
- **Shared (default):** Both teams may challenge and acquire the same spellcard. Cells can be completed independently by each team.
- **Exclusive:** Each cell can be completed by only one team. Both teams may SELECT (pending) the same cell, but only the first to complete it wins. A team cannot SELECT a cell the opponent has already completed.
- **Exclusive cooldown:** After a team completes a spellcard in exclusive mode, it must wait for a cooldown before completing the next one (selection is still allowed during cooldown).

Spellcards are classified into different difficulty levels and assigned scores accordingly. Each bingo (row, column, diagonal) grants a bonus (fixed in shared mode; `2×N` per line in exclusive mode).

For a recording example, watch [this video](https://www.bilibili.com/video/BV1gQ2rBQEDC/?t=2610) (starts at ~43:30).


---

## Deployment

### Quick start

Requirements:
- Python 3.10+
- Install dependencies: `pip install -r requirements.txt`
- Data files: `data/SpellcardDataNormal.csv`, `data/SpellcardDataLunatic.csv`

Run the server:

```bash
python app.py [--mode shared|exclusive] [--size N] [--pool normal|lunatic] [--port P]
```

- `--mode`: server default for new rooms (default: `shared`). New rooms can override via the lobby mode selector.
- `--size`: grid size N (default 5). The board is N×N. Serves as default for new rooms.
- `--pool`: default spellcard pool for new rooms (default: `normal`). New rooms can override via the lobby pool selector.
- `--port`: port to listen on (default: 5000).

Open http://localhost:5000 in a browser (or the port you specified).

### Online play

Two players (or parties) play over the internet, each representing a team (RED or BLUE). You can also join as an observer:

1. Each player opens the app and is directed to the **lobby**.
2. Both enter the same **room ID** (e.g. `abc123`), select **mode** (Shared/Exclusive), **pool** (Normal/Lunatic), and choose their **team** (RED/BLUE/Observer).
3. Click **Join** to join the game. The first player to join a room sets mode/pool; all players in that room share the same mode/pool.
4. Each client is fixed to its role; RED/BLUE can interact with their team, and **Observer** is read-only.
5. State is synced in real time via Server-Sent Events. Room state persists across server restarts.

See `docs/online-adaptation.md` for the full design.

### Top HUD UI

- Left and right: team titles “RED” and “BLUE”.
- Center row labels: “score” and “hp”.
- In exclusive mode, HUD also shows `CD` (cooldown): remaining seconds or `✅` when ready.
- Under each team title you’ll see the team’s total score and its HP controls.
- Your team is indicated by “you” under the team label; controls for the other team are display-only.
- Observer view shows a dedicated observer indicator and marks both team selectors as guest.

### Clicking cells (core logic)

For your team, cell clicks cycle through these states:

1. Unchecked → Pending
2. Pending → Checked
3. Checked → Unchecked

- A team can have at most one Pending cell at a time. Clicking an Unchecked cell when the team already has a Pending cell will move the Pending marker to the new cell.
- **Exclusive mode:** You cannot SELECT (Pending) a cell the opponent has already completed. When you complete a cell, the opponent’s Pending on that cell (if any) is cleared.

### Adjusting HP

- Each team has per-cell HP controls “- hp +” under the HUD.
- HP is tied to that team’s current Pending cell:
	- When a team has a Pending cell, its HP value appears and the “-”/“+” buttons are enabled.
	- If the team has no Pending cell, HP shows “--” and the buttons are disabled.

### Resetting the game

Click “Reset” to reinitialize everything.

- Observer cannot reset/click/adjust HP.

### Scoring

- Per‑cell scores come from the data file and are shown in the bottom‑right of each cell.
- Team totals are calculated on the server (see `calc_score.py`) from the sum of checked cells and bingo bonus.

### Persistence

- Room state is saved to `data/rooms/{room_id}/state.json` after each mutation (click, hp, reset).
- State persists across server restarts; rooms are loaded on first access.
- Each room stores its game mode/pool (set by the first joiner) and grid size. Mode/pool are per-room; different rooms can use different combinations.
- If you start the server with a different default `--size` or try to join a room with a different selected pool than the room already uses, the room is treated as incompatible. The app will prompt you to use a new Room ID; existing room data is never overwritten.

---

## Configurable Settings

> Command line (`python app.py`)

1. `--mode`: default game mode for new rooms (`shared` or `exclusive`). Default: `shared`. Each room can have its own mode (set in the lobby when the room is first created).
2. `--size`: grid size N. Default: `5`. Serves as default for new rooms.
3. `--pool`: default spellcard pool key for new rooms (`normal` or `lunatic`). Default: `normal`.
4. `--port`: listening port. Default: `5000`.

> defs.py

1. `max_hp`: per spellcard+team HP
2. `SPELLCARD_POOLS`: spellcard pool key -> CSV path mapping.
3. `privileged_spellcard_ids`: per-pool special spellcards guaranteed to sample.
4. `exclusive_mode_cooldown`: cooldown seconds after completion in exclusive mode.
5. `show_reset_button`: whether to show the Reset button on the frontend (hide to avoid accidental clicks).

> calc_score.py

1. `def line_score(line_values: List[int], bingo_bonus_val: int = None) -> int`: how bingo bonus is calculated. Online rooms use `2×N` in exclusive mode.

See `docs/exclusive-mode.md` and `docs/exclusive-cooldown.md` for exclusive mode and cooldown details.

---

## UI details

- Cell name rendering: two-line clamp with a display-width heuristic (ASCII ≈ 1 unit, CJK ≈ 2 units) to keep names readable within 72×72 cells.
- Comment rendering: font size adapts heuristically based on length so most comments fit within a ~28px tall area below the name; color flips to white when the cell is checked for contrast.
- Pending state outline: visible border in the active team color, extending slightly outside the cell box for stage visibility.
- Score: circled numerals at bottom-right for scores up to 20; larger scores fall back to plain text.
- Layout: team labels show "you" for your side; the center column keeps a fixed width so alignment remains stable whether the Reset button is visible or hidden.

---

