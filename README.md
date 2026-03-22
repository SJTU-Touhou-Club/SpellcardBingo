# Spellcard Bingo!

This repository contains the UI for the Spellcard Bingo game used at the SJTU Touhou Festival 2025.

---

## Credits

- This project is inspired by [th-bingo](https://github.com/CuteReimu/th-bingo).

- 落星, 带鸽子 @ SJTU
	- Project proposal
	- Spellcard data collection and scoring
- fAKe @ SJTU
	- Core code design and implement.
- Copilot 様 
	- GPT-5@OpenAI and Gemini 3.0 Pro@Google
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

Two teams compete to gain higher scores, where each team member can challenge a limited number of spellcards. (Two teams may challenge and acquire same spellcard.)

Spellcards are classified into different difficulty levels and assigned scores accordingly. Each bingo (row, column, diagonal) grants a bonus.

For a recording example, watch [this video](https://www.bilibili.com/video/BV1gQ2rBQEDC/?t=2610) (starts at ~43:30).


---

## Deployment

### Quick start

Requirements:
- Python 3.10+
- Install dependencies: `pip install -r requirements.txt`
- Data file: `data/SpellcardData.csv`

Run the server:

```bash
python app.py
```

Open http://localhost:5000 in a browser.

### Online play

Two players (or parties) play over the internet, each representing a team (RED or BLUE):

1. Each player opens the app and is directed to the **lobby**.
2. Both enter the same **room ID** (e.g. `abc123`) and choose their **team** (RED or BLUE).
3. Click **Play** to join the game. Multiple connections per team are allowed (reconnect-friendly).
4. Each client is fixed to its team; cell clicks and HP adjustments affect that team only.
5. State is synced in real time via Server-Sent Events. Room state persists across server restarts.

See `docs/online-adaptation.md` for the full design.

### Top HUD UI

- Left and right: team titles “RED” and “BLUE”.
- Center row labels: “score” and “hp”.
- Under each team title you’ll see the team’s total score and its HP controls.
- Your team is indicated by “you” under the team label; controls for the other team are display-only.

### Clicking cells (core logic)

For your team, cell clicks cycle through these states:

1. Unchecked → Pending
2. Pending → Checked
3. Checked → Unchecked

- A team can have at most one Pending cell at a time. Clicking an Unchecked cell when the team already has a Pending cell will move the Pending marker to the new cell.

### Adjusting HP

- Each team has per-cell HP controls “- hp +” under the HUD.
- HP is tied to that team’s current Pending cell:
	- When a team has a Pending cell, its HP value appears and the “-”/“+” buttons are enabled.
	- If the team has no Pending cell, HP shows “--” and the buttons are disabled.

### Resetting the game

Click “Reset” to reinitialize everything.

### Scoring

- Per‑cell scores come from the data file and are shown in the bottom‑right of each cell.
- Team totals are calculated on the server (see `calc_score.py`) from the sum of checked cells and bingo bonus.

### Persistence

- Room state is saved to `data/rooms/{room_id}/state.json` after each mutation (click, hp, reset).
- State persists across server restarts; rooms are loaded on first access.

---

## Configurable Settings

> defs.py

1. `N`: size of the grid
2. `max_hp`: per spellcard+team HP
3. `privileged_spellcard_ids`: special spellcards that are guaranteed to sample.
4. `show_reset_btn`: whether to show the Reset button on the frontend (hide to avoid accidental clicks).

> calc_score.py
1. `def line_score(line_values: List[int]) -> int`: how bingo bonus is calculated.

---

## UI details

- Cell name rendering: two-line clamp with a display-width heuristic (ASCII ≈ 1 unit, CJK ≈ 2 units) to keep names readable within 72×72 cells.
- Comment rendering: font size adapts heuristically based on length so most comments fit within a ~28px tall area below the name; color flips to white when the cell is checked for contrast.
- Pending state outline: visible border in the active team color, extending slightly outside the cell box for stage visibility.
- Score: circled numerals at bottom-right for scores up to 20; larger scores fall back to plain text.
- Layout: team labels show "you" for your side; the center column keeps a fixed width so alignment remains stable whether the Reset button is visible or hidden.

---

