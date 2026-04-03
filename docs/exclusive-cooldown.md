# Spellcard Bingo — Exclusive Cooldown Design

**Document status:** Design (implemented)  
**Version:** 1.0

---

## 1. Goal

In **exclusive** mode only, each team gets a cooldown after completing a spellcard:

- Config key: `exclusive_mode_cooldown` (seconds, default `30`)
- Team can still **select** (set PENDING) during cooldown
- Team **cannot complete** (PENDING -> CHECKED) while cooldown is active

This slows rapid chain-completes and makes race timing more visible.

---

## 2. Rules

### 2.1 Start cooldown

When a team completes a spellcard in exclusive mode (`PENDING -> CHECKED`):

- Set that team's cooldown end timestamp to `now + exclusive_mode_cooldown`

### 2.2 Block completion during cooldown

If the same team clicks a `PENDING` cell while cooldown is active:

- Reject completion
- Keep cell state as `PENDING`

### 2.3 Cancel resets cooldown immediately

If a team cancels a completed cell (`CHECKED -> UNCHECKED`), treat it as misclick correction:

- Reset that team's cooldown to `0` immediately (no wait)

### 2.4 Shared mode

- Cooldown is ignored in shared mode (always inactive)

---

## 3. State Model

Per-room state adds:

- `team_cooldown_until`: `{ red: <unix_ts>, blue: <unix_ts> }`

Persist in `data/rooms/{room_id}/state.json`.

---

## 4. API / Payload

`/state` adds:

- `cooldown`: `{ red: <seconds_remaining>, blue: <seconds_remaining> }`

`seconds_remaining` is an integer (`0` when inactive).

---

## 5. Frontend UI

HUD adds a new row under HP:

- Label: `CD`
- Per team value:
  - active cooldown: `N s`
  - inactive: `✅`

Observer is still read-only and only views countdown updates.

---

## 6. Notes

- Cooldown is server-authoritative.
- Countdown continues naturally across reconnects/reloads because the absolute timestamps are persisted.
