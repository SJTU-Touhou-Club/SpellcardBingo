# Spellcard Bingo — Exclusive Mode Design Document

**Document status:** Design (implemented)  
**Version:** 1.0

---

## 1. Executive Summary

This document describes the **exclusive** (competitive/fighting) game mode for Spellcard Bingo. In exclusive mode, each cell can be completed by only one team—first to complete wins the cell, and the opponent cannot select or complete that cell. This contrasts with the default **shared** mode, where both teams can harvest the same spellcard independently.

---

## 2. Mode Comparison

| Aspect | Shared Mode (default) | Exclusive Mode |
|--------|----------------------|----------------|
| **Cell ownership** | Both teams can CHECK the same cell | At most one team can CHECK a cell |
| **PENDING on same cell** | Each team has independent PENDING | Both can have PENDING; first to complete wins |
| **Selecting opponent's cell** | N/A | Team cannot SELECT (PENDING) a cell the opponent has CHECKED |
| **Bingo bonus** | Fixed (from defs) | `2 * N` per line |
| **Naming** | Cooperative/shared | Competitive/exclusive/fighting |

---

## 3. Cell State Transitions (Exclusive Mode)

### 3.1 UNCHECKED → PENDING (Select)

- **Allowed** only if the **other** team does not have this cell CHECKED.
- If the opponent has completed the cell, the click is rejected (no state change).
- Same PENDING rules as shared: clear current team's existing PENDING elsewhere before setting new PENDING.

### 3.2 PENDING → CHECKED (Complete)

- Team completes the cell.
- **Side effect:** Clear the **other** team's PENDING on this cell (they lost the race).
- Cell is now owned by this team; opponent can no longer select it.

### 3.3 CHECKED → UNCHECKED (Revert)

- Only the owning team can revert.
- Same as shared mode: cell becomes available for both teams again.

---

## 4. Bingo Bonus

- **Shared mode:** Uses fixed `bingo_bonus` from `defs.py`.
- **Exclusive mode:** Bingo bonus per line = `2 * N`, where `N` is the grid size.

---

## 5. Room Compatibility

### 5.1 Persisted Data

Room state (`data/rooms/{room_id}/state.json`) includes:

- `mode`: `"shared"` or `"exclusive"`
- `size`: grid dimension `N`

### 5.2 Compatibility Rules

- Server is started with `--mode` and `--size` (defaults: shared, 5).
- When loading a room from disk:
  - If room's `mode` or `size` differs from server config → **incompatible**.
  - Do **not** load, overwrite, or create a new room with that ID.
  - Return incompatibility info so the client can prompt the user.

### 5.3 Backward Compatibility

- Older `state.json` files without `mode` or `size`:
  - Treat missing `mode` as `"shared"`.
  - Infer missing `size` from `spellcard_id_map` (assume square grid).

---

## 6. CLI and Server Configuration

```bash
python app.py [--mode shared|exclusive] [--size N]
```

- `--mode`: `shared` (default) or `exclusive`
- `--size`: grid size `N` (default `5`)

---

## 7. Client Handling

- **Lobby:** On join, if the room exists and is incompatible, show an alert; do not redirect to the game. Guide user to use a new Room ID.
- **Game page:** If `/state` returns 400 with `incompatible: true`, show a popup with the same message and a link back to the lobby.
- **No overwrite:** The server never overwrites an incompatible room file.
