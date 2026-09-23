# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project state

This repository is currently **pre-implementation**: it contains only [PLAN.md](PLAN.md) (the full build spec) and an empty [Pipfile](Pipfile)/[Pipfile.lock](Pipfile.lock) pinned to Python 3.14 with no dependencies declared yet. None of the directories described below exist yet — they are the plan, not the current layout. There is no git repository initialized in this directory yet.

**Always read PLAN.md in full before starting work.** It is the authoritative spec — the summary below is only a navigation aid. Work through the build phases in [PLAN.md §7](PLAN.md) **in order**; each phase has explicit acceptance criteria that must pass before moving to the next.

## What this project is

A LeRobot-powered maths game for children (a "Robot Maths Tutor"). A robot arm places coloured shapes into two boxes to set up a sum (e.g. `3 + 2 = ?`); the child answers by laying coloured cylinder bars on a mat; an overhead camera counts everything, and a PySide6 GUI drives the game and shows feedback. See [PLAN.md §1–2](PLAN.md) for the full physical setup and game design (round rules, operand constraints, answer-submission timing).

## Environment

- Dependency management is via **Pipenv** (`pipenv install`, `pipenv run ...`); Python 3.14 is required per the Pipfile. As implementation starts, dependencies will need to be added to the Pipfile — PLAN.md names the intended stack: **PySide6** (GUI), **OpenCV** (vision), **MediaPipe** (hand detection), **lerobot** (robot control/policies), and optionally **Ultralytics YOLO** (if classical CV counting isn't accurate enough).
- Target host is **macOS (Apple Silicon)**. Camera permissions must be granted to the terminal/IDE running the app, and camera indices should be selected by name/unique ID (they can change on USB replug).
- The `lerobot` CLI's command names have changed across versions — verify against the installed version before using them (newer versions use `lerobot-find-port`, `lerobot-find-cameras`, `lerobot-calibrate`, `lerobot-teleoperate`, `lerobot-record`, `lerobot-train`).

## Planned architecture (PLAN.md §3)

A **single Python process** is required — this is a deliberate constraint, not a style choice: on macOS, only one process can own a given camera, and both the `overhead` and `wrist` cameras are shared between the game logic and any policy inference.

```
app/
  main.py              # entry point, starts GUI
  config.yaml          # ports, camera indices, ROIs, thresholds, policy paths
  gui/                 # PySide6 screens: start, round, end
  game/
    engine.py          # state machine, score, round generation
    problems.py        # operand/operation generation with constraints
  vision/
    cameras.py          # CameraManager: owns both cameras, threaded frame grabber
    calibration.py      # table homography from tape corners, ROI definitions
    counter.py           # count pieces in LEFT_BOX / RIGHT_BOX / MARGIN, bars on MAT
    hands.py              # hand-over-mat detection
    debug_view.py         # overlay drawing for debugging
  robot/
    interface.py        # abstract RobotController: place_to(box), return_from(box), go_home()
    lerobot_ctrl.py     # real implementation running trained LeRobot policies
    mock_ctrl.py         # fake robot for development
scripts/
  calibrate_board.py   # click tape corners on overhead image -> saves homography + ROIs
  capture_samples.py   # save overhead frames for tuning/labelling
  test_counter.py       # run counter live with overlays
training/README.md      # exact record/train commands used
tests/
```

Key points to keep in mind when implementing against this layout:

- **Threading**: robot control and vision must run in worker threads (Qt `QThread` + signals) — never block the GUI thread. Every game-engine state transition emits a signal the GUI reacts to.
- **`RobotController` abstraction** ([interface.py](PLAN.md)): the game only ever calls `place_to(box)` / `return_from(box)` / `go_home()`. Three interchangeable implementations exist by design — `mock_ctrl.py` (dev, no hardware), `lerobot_ctrl.py` (trained ACT/SmolVLA policies), and a scripted-IK fallback — so the game logic must never depend on which one is active.
- **Robot skill simplification**: the robot only needs 3 learned skills (`place_left`, `place_right`, `return_piece` per box) — the game cares only about *how many* pieces are in each box, not which piece. Every skill run starts and ends at a fixed home pose.
- **Ground truth comes from vision, not intent**: after the robot places pieces, the overhead camera re-counts each box, and *that* count — not what the robot was commanded to do — becomes the displayed sum. Retry on mismatch before accepting reality.
- **Reset optimisation**: between rounds, only the *difference* between current and next box counts is moved (not a full empty/refill), to save robot time.
- **Game state machine** (`engine.py`, full transitions in [PLAN.md §3](PLAN.md)): `START_PAGE → NEW_GAME → ROUND_SETUP → WAIT_FOR_ANSWER → EVALUATE → FEEDBACK → ROUND_RESET → (loop or END_SCREEN)`.
- **Answer submission** is gated on three conditions together (hand seen at least once, hand clear for `HAND_CLEAR_SECONDS`, bar count stable for `COUNT_STABLE_SECONDS`) — see [PLAN.md](PLAN.md) "When is an answer submitted?" for exact semantics before touching that logic.
- **Facilitator hotkeys** are load-bearing for demo safety, not optional debug cruft: `Space` force-submit, `N` skip round, `R` robot home, `M` manual count override, `Esc` emergency stop (torque off).
