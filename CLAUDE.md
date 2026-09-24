# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project state

**Phase 1 (skeleton + GUI + mock robot + mock vision) is done and passing its accept criteria** — see [PLAN.md §7](PLAN.md). The `app/` layout below is real, not just planned. Phases 2–6 (real cameras, real vision, trained robot skills, integration, polish) are not started.

**Always read PLAN.md in full before starting work.** It is the authoritative spec — the summary below is only a navigation aid. Work through the build phases in [PLAN.md §7](PLAN.md) **in order**; each phase has explicit acceptance criteria that must pass before moving to the next. The robot-policy decision for Phase 4 is already locked in (ACT, scoped to `place_left`/`place_right` as required — see PLAN.md §4/§9).

## What this project is

**Arithma** — a LeRobot-powered maths game for children. A robot arm places coloured shapes into two boxes to set up a sum (e.g. `3 + 2 = ?`); the child answers by laying coloured cylinder bars on a mat; an overhead camera counts everything, and a PySide6 GUI drives the game and shows feedback. See [PLAN.md §1–2](PLAN.md) for the full physical setup and game design (round rules, operand constraints, answer-submission timing).

## Environment

- Dependency management is via **Pipenv** (`pipenv install`, `pipenv run ...`); Python 3.14 is required per the Pipfile. Installed so far: **PySide6** (GUI), **PyYAML** (config), **pytest** (dev). Not yet added — needed from Phase 2 onward per PLAN.md's stack: **OpenCV** (vision), **MediaPipe** (hand detection), **lerobot** (robot control/policies), optionally **Ultralytics YOLO**.
- Target host is **macOS (Apple Silicon)**. Camera permissions must be granted to the terminal/IDE running the app, and camera indices should be selected by name/unique ID (they can change on USB replug).
- The `lerobot` CLI's command names have changed across versions — verify against the installed version before using them (newer versions use `lerobot-find-port`, `lerobot-find-cameras`, `lerobot-calibrate`, `lerobot-teleoperate`, `lerobot-record`, `lerobot-train`).

## Commands

- Run the app: `pipenv run python -m app.main` (from repo root).
- Run all tests: `pipenv run pytest tests/`. Run a single file: `pipenv run pytest tests/test_engine.py`; a single test: `pipenv run pytest tests/test_engine.py::test_submits_once_all_three_conditions_hold`.
- The GUI smoke test (`tests/test_gui_smoke.py`) drives the real app end-to-end (real button clicks, real state machine, no display needed) via `QT_QPA_PLATFORM=offscreen` — set automatically by the test file itself, no special invocation needed. It plays a full 10-round game and verifies the score. See that file's module docstring before changing it: driving a live background `QThread` with simulated timing in an automated test is inherently racy in ways that don't matter at real human-paced timings — the fix used there is retry-until-observed-effect, not fixed delays.

## Working with the game engine

`app/game/engine.py`'s `GameEngine` is deliberately Qt-free (plain Python, callback-based) so it can be unit tested directly and run in any worker thread; `app/gui/engine_thread.py` is the thin `QThread` wrapper that turns its callbacks into Qt signals for the GUI. Facilitator hotkey methods (`request_force_submit`, `request_skip_round`, `request_stop`, `request_go_home`) just set flags/call through — they don't block — so the engine's own poll loop (`POLL_INTERVAL_SECONDS`, currently 0.1s) picks them up on its next iteration. `_wait_for_answer` resets its per-round flags at the very start of each round; a caller that fires a hotkey at exactly that moment can have it silently cleared, which is why anything driving the engine programmatically (tests, future scripted demos) should treat these requests as safe to resend rather than one-shot.

## Architecture (PLAN.md §3)

A **single Python process** is required — this is a deliberate constraint, not a style choice: on macOS, only one process can own a given camera, and both the `overhead` and `wrist` cameras are shared between the game logic and any policy inference.

```
app/
  main.py              # entry point, starts GUI                                  [done]
  config.yaml          # ports, camera indices, ROIs, thresholds, policy paths     [done: game/mock sections only; cameras/robot/vision sections are placeholders for Phase 2+]
  gui/                 # PySide6 screens: start, round, end                       [done]
    main_window.py     # wires screens + mocks + EngineThread together
    engine_thread.py   # QThread wrapper: re-emits GameEngine's callbacks as Qt signals
    start_screen.py / round_screen.py / end_screen.py
  game/
    engine.py          # state machine, score, round generation                   [done]
    problems.py        # operand/operation generation with constraints            [done]
  vision/
    board_state.py     # shared BoardState dataclass (left/right/margin/bars/hand_on_mat/stable)  [done]
    mock_vision.py      # keyboard-driven mock (Phase 1)                          [done]
    cameras.py / calibration.py / counter.py / hands.py / debug_view.py           [Phase 2/3, not started]
  robot/
    interface.py        # abstract RobotController: place_to(box), return_from(box), go_home()  [done]
    mock_ctrl.py         # fake robot for development                             [done]
    lerobot_ctrl.py     # real implementation running trained LeRobot policies    [Phase 4, not started]
scripts/                # calibrate_board.py, capture_samples.py, test_counter.py [Phase 2/3, not started]
training/README.md      # exact record/train commands used                       [Phase 4, not started]
tests/
  test_problems.py, test_engine.py, test_gui_smoke.py                             [done]
```

Key points to keep in mind when implementing against this layout:

- **Threading**: robot control and vision must run in worker threads (Qt `QThread` + signals) — never block the GUI thread. Every game-engine state transition emits a signal the GUI reacts to.
- **`RobotController` abstraction** ([interface.py](app/robot/interface.py)): the game only ever calls `place_to(box)` / `return_from(box)` / `go_home()`. Interchangeable implementations exist by design — `mock_ctrl.py` (dev, no hardware, done), `lerobot_ctrl.py` (trained ACT policies — not SmolVLA, see PLAN.md §4 for why; not started), and a scripted-IK fallback — so the game logic must never depend on which one is active.
- **Robot skill simplification**: the robot only needs 3 learned skills (`place_left`, `place_right`, `return_piece` per box) — the game cares only about *how many* pieces are in each box, not which piece. Every skill run starts and ends at a fixed home pose.
- **The sum comes from the robot commands, not vision** (changed from the original plan): the displayed sum is how many times the game called `place_to("left")` / `place_to("right")` plus the operator. Boxes are never re-counted; the overhead camera is only used on the answer mat (bars + hands). A helper resets the shapes between rounds and presses Enter (no `return_*` skills).
- **Reset optimisation**: between rounds, only the *difference* between current and next box counts is moved (not a full empty/refill), to save robot time.
- **Game state machine** (`engine.py`, full transitions in [PLAN.md §3](PLAN.md)): `START_PAGE → NEW_GAME → ROUND_SETUP → WAIT_FOR_ANSWER → EVALUATE → FEEDBACK → ROUND_RESET → (loop or END_SCREEN)`.
- **Answer submission** is gated on three conditions together (hand seen at least once, hand clear for `HAND_CLEAR_SECONDS`, bar count stable for `COUNT_STABLE_SECONDS`) — see [PLAN.md](PLAN.md) "When is an answer submitted?" for exact semantics before touching that logic.
- **Facilitator hotkeys** are load-bearing for demo safety, not optional debug cruft: `Space` force-submit, `N` skip round, `R` robot home, `M` manual count override, `Esc` emergency stop (torque off).
