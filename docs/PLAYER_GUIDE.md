# Player Guide — game logic reference and testing

The Player tab runs your game inside the editor, using an engine that
faithfully mirrors the C64 behavior. Design, test, and iterate without
any export/compile cycle; build the disk when it plays right.

## Rooms, objects, movement

- Every room has an ID (1–20), name, description, and four exits
  (North/South/East/West). Exit `0` = no exit.
- Objects live in a start room. `TAKEABLE` objects can be picked up;
  `FIXED` objects (scenery, creatures, gates) cannot.
- Players move with `N`/`S`/`E`/`W` (or synonyms you define), pick
  things up with `TAKE`, check `INVENTORY` (`I`), and `EXAMINE` things.

## Responses — the heart of your game

Each response is: **COMMAND : CONDITION : MESSAGE : ACTION**

```
EXAMINE GATE::THE GATE HAS A LARGE KEYHOLE.:
USE KEY GATE:HAS KEY:THE GATE CREAKS OPEN!:UNLOCK WEST 2 TO 6
HIT BEAST:HAS SWORD,AT 7:THE BEAST FALLS!:SET FLAG.BEAST_DEAD,REMOVE BEAST,SCORE 50
TALK WIZARD:AT 4::MSG WIZARD_GREETING
GIVE CHALICE WIZARD:HAS TREASURE,AT 4:HE THANKS YOU!:SCORE 150,WINXXX
```

Responses are checked top to bottom; the first match wins. Multiple
conditions (comma-separated) must ALL be true.

### Conditions

| Condition        | True when...                                  |
|------------------|-----------------------------------------------|
| `HAS OBJ`        | the player is carrying OBJ                    |
| `AT n`           | the player is in room n                       |
| `FLAG.NAME`      | the flag NAME has been set                    |
| `NOT FLAG.NAME`  | the flag NAME has not been set                |

### Actions (comma-separated, run in order)

| Action                       | Effect                                        |
|------------------------------|-----------------------------------------------|
| `SET FLAG.NAME`              | set a flag (remembered game state)            |
| `REMOVE OBJ`                 | remove an object from the game (e.g. a slain beast) |
| `SCORE n`                    | add n points                                  |
| `MSG KEY`                    | show a message from the Messages tab          |
| `UNLOCK <DIR> <FROM> TO <TO>`| open a new exit (e.g. `UNLOCK WEST 2 TO 6`)   |
| `MOVE TO n`                  | teleport the player to room n                 |
| `WINXXX`                     | win the game (with play-again prompt)         |

## Debug mode

Player tab → **Debug** shows, for every command you type:

- `PARSED:` how your input was split into verb and object
- `MATCHED:` which response rule fired (or none)
- `[ACTION]` each state change (score, flags, unlocks)
- `MOVED to room n` for navigation

If a command misbehaves: turn on Debug, type it again, and check —
did it parse the way you expected? Did the right rule match? Which
condition failed?

Common cases:
- **"I DON'T UNDERSTAND THAT."** — no response matches; check spelling
  and that the object is defined
- **"YOU CAN'T GO THAT WAY."** — that exit is 0 (or not yet UNLOCKed)
- **Right rule, wrong branch** — check condition order; the first
  matching response wins

## Testing vs. the real C64

The Player tab and the built `.d64` play the same game, with small
differences to know about:

- The C64 game shows the room picture on the top of the screen; the
  Player tab is text-only (by design — it's the fast iteration loop).
- On the C64 (StoryTllr engine), score points always add up; the
  "Max Score" setting is ignored there.
- Commands with two objects (like `USE KEY GATE`) additionally require
  the second object to be present in the room on the C64 — usually
  exactly what you want.

The export step lists anything in your game that needs attention, in
plain language, before building.
