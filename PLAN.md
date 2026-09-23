# Robot Maths Tutor — Project Plan

A LeRobot-powered maths game for children. The robot arm sets up a sum by placing
coloured shapes into two taped boxes; the child answers by laying thin cylinders
("answer bars") on a black mat; an overhead camera counts everything and marks the answer.

This document is the build plan for Claude Code. Work through the phases in order.
Each phase has acceptance criteria — do not move on until they pass.

---

## 1. The physical setup (what the cameras will see)

- **Follower arm** (LeRobot SO-100/SO-101) at the top edge of the table, **leader arm** used only for teleoperation / data recording.
- **Two boxes** marked with purple tape, side by side: `LEFT_BOX` and `RIGHT_BOX`.
- **Margin**: ~15 coloured wooden pieces (cubes/rectangles, cylinders, triangles, hexagons; red, blue, green) placed around the outside of the boxes. This is the robot's supply.
- **Answer mat**: dark grey/black sheet on the learner's side, below the boxes.
- **Answer bars**: ~11 thin coloured cylinders (red, blue, green, yellow) that the child places on the mat. **Max answer is therefore 10** (keep one spare).
- **Cameras**:
  - `overhead` — fixed, sees the whole board. Used for all game logic (counting, hand detection) and as a policy input.
  - `wrist` — on the gripper. Used as a policy input only.
- Lighting: ring light, kept constant across data collection and play.
- Host: macOS (Apple Silicon assumed).

---

## 2. Game design

### Screens (GUI)
1. **Welcome / Start page** — friendly title, short "how to play", big **Start** button, small **Quit** button.
2. **Round screen** — shows:
   - `Round N / 10` and current score
   - the sum in large type, e.g. `3 + 2 = ?` (operator shown big and colourful: `+ − ×`)
   - a status line / mascot message for the current state:
     - "Watch the robot…" (robot setting up)
     - "Count the shapes and put your answer on the black mat!"
     - "Take your hands away when you're done" (hand detected)
     - "Checking…"
     - "Well done! ✓" / "Not quite — the answer was 5" (with a count visual)
     - "Please clear the mat" (before next round)
   - optional live overhead camera preview (toggle, off by default for kids; on for demo/debug)
3. **End screen** — final score `7 / 10` with stars/celebration, buttons **Play again** (new 10-round game) and **Exit** (back to Start page). The Start page's **Quit** closes the app.

### Round rules
- The program chooses an operation (+, −, ×) and two operands.
- Robot places `a` pieces into `LEFT_BOX` and `b` pieces into `RIGHT_BOX`.
- The child counts, then places `answer` bars on the mat.
- Operand constraints (keep robot time low and answers ≤ 10):
  - `+`: a, b ∈ 1..5, a + b ≤ 10
  - `−`: a ∈ 2..6, b ∈ 1..a−1 (no negatives, no zero answers at first)
  - `×`: a, b ∈ 1..3 (and a×b ≤ 10), left box = groups, right box = items per group — show this in the GUI text ("2 groups of 3")
  - Also cap `a + b ≤ available margin pieces`.
- Balance the 10 rounds: roughly 4 add, 3 subtract, 3 multiply; optional difficulty ramp.

### When is an answer submitted?
Mark the answer only when **all** of these hold:
1. A hand has been seen over the mat at least once since the round started (avoids marking an empty mat immediately).
2. No hand has been detected over the mat for `HAND_CLEAR_SECONDS` (default 2.0 s).
3. The bar count has been stable for `COUNT_STABLE_SECONDS` (default 1.5 s).

Then evaluate and show feedback. Before the next round starts, wait until the mat is clear (bar count = 0 and no hand) — or allow a facilitator key to skip.

### The sum comes from the robot commands (updated 2026-09-23)
The sum shown is what the game **commanded**: how many times it called `place_left` / `place_right`, plus the chosen operator. The boxes are **not** re-counted, so a dropped or misplaced piece never changes the expected answer. Failed placements are only logged as a robot-reliability metric. The overhead camera is used only on the answer mat (bar count + hand detection). Between rounds a helper puts the shapes back on their margin spots and presses **Enter**.

---

## 3. Architecture

Single Python process (avoids fighting over cameras on macOS — only one process should open each camera).

```
robot-maths-tutor/
  app/
    main.py              # entry point, starts GUI
    config.yaml          # ports, camera indices, ROIs, thresholds, policy paths
    gui/                 # PySide6 screens: start, round, end
    game/
      engine.py          # state machine (see below), score, round generation
      problems.py        # operand/operation generation with constraints
    vision/
      cameras.py         # CameraManager: owns both cameras, threaded frame grabber, shares latest frames
      calibration.py     # table homography from tape corners, ROI definitions
      counter.py         # count pieces in LEFT_BOX / RIGHT_BOX / MARGIN, bars on MAT
      hands.py           # hand-over-mat detection
      debug_view.py      # overlay drawing for debugging
    robot/
      interface.py       # abstract RobotController: place_to(box), return_from(box), go_home()
      lerobot_ctrl.py    # real implementation running trained LeRobot policies
      mock_ctrl.py       # fake robot for development (sleeps, logs, can "place" by prompting a human)
  scripts/
    calibrate_board.py   # click tape corners on overhead image → saves homography + ROIs
    capture_samples.py   # save overhead frames for tuning/labelling
    test_counter.py      # run counter live with overlays
  training/
    README.md            # exact record/train commands used
  tests/
```

### Game state machine (`engine.py`)
```
START_PAGE
  → (Start) NEW_GAME
NEW_GAME → ROUND_SETUP
ROUND_SETUP        # choose problem, command robot, verify box counts (retry up to 2x)
  → WAIT_FOR_ANSWER
WAIT_FOR_ANSWER    # watch mat: hand seen? hand gone? count stable?
  → EVALUATE
EVALUATE → FEEDBACK (3–4 s)
FEEDBACK → ROUND_RESET
ROUND_RESET        # robot adjusts boxes for next round; wait for mat to be clear
  → ROUND_SETUP (if round < 10) | END_SCREEN
END_SCREEN → NEW_GAME (Play again) | START_PAGE (Exit)
```
- Robot and vision work must run in worker threads (Qt `QThread`/signals), never on the GUI thread.
- Every state emits a signal the GUI uses to update the status message.
- Facilitator hotkeys (for demo safety): `Space` = force-submit answer, `N` = skip round, `R` = robot go home, `M` = manual count override, `Esc` = emergency stop (torque off / stop policy).

### Reset optimisation
Instead of emptying both boxes every round, compute the **difference** between current and next box counts and only move that many pieces (box→margin or margin→box). This roughly halves robot time.

---

## 4. Robot control strategy

### Key simplification
The game only cares **how many** pieces are in each box, not which piece. So the robot only needs **three skills**:

| Skill | Instruction | Meaning |
|---|---|---|
| `place_left` | "Pick a piece from the margin and place it in the left box" | +1 left |
| `place_right` | "Pick a piece from the margin and place it in the right box" | +1 right |
| `return_piece` | "Pick a piece from a box and put it back on the margin" (variants per box: `return_left`, `return_right`) | −1 box |

Each skill call moves **one** piece and ends with the arm back at a fixed **home pose** (important: every demonstration must end at home, so the policy learns to finish cleanly and the overhead camera has a clear view).

`RobotController.place_to("left")` = run the skill policy until (a) the overhead count for that box increases by 1 **and** the arm is near home, or (b) timeout (e.g. 25 s). Then verify, retry if needed.

### Policy decision: ACT, scoped to 2 required skills (hackathon, 1-day build)
Decided (2026-09-23) — this is a hackathon build with ~1 day and a requirement to demonstrate an actual trained/learned policy, not scripted motion.

- **Model: ACT, one small model per skill** (~80M params). Not SmolVLA: a documented SO-101 pick-place run needed 75 tightly-constrained episodes to succeed after 50 episodes over a wider workspace failed outright, and SmolVLA training alone runs ~4h (A100) to ~10h (RTX 3090) per skill — too slow and too data-sensitive for a single day. ACT trains in ~30–90 min on a cloud GPU (~8–12h on CPU) and is reliable with ~50 episodes, so a bad first run can still be diagnosed and retrained same-day. Load all trained models at startup; switch model per call.
- **Required today: `place_left`, `place_right`.** This is the core "watch the robot set up the sum" moment and runs every round — train and eval these first.
- **Stretch (not required for Day 1): `return_left`, `return_right`.** These only exist for the delta-based reset optimisation below; if they don't get trained today, fall back to a manual/scripted box reset between rounds for the demo. This doesn't weaken the "learned policy" story since the headline skills the audience watches are still ACT-trained.
- No pretrained checkpoint is reused for the arm policy itself — pick-and-place policies are scene/embodiment-specific and nothing on the Hub fits this custom rig (tape boxes, specific pieces, camera pose). `lerobot/svla_so101_pickplace` is a useful reference for config/camera setup only, not usable weights.
- **Fallback (if `place_left`/`place_right` aren't reliable by demo time):** scripted pick-and-place using overhead-camera piece positions → table coordinates (homography) → inverse kinematics from the SO-101 URDF, fixed top-down grasp. Keep the `RobotController` interface identical so the game doesn't care.

### Data collection rules (teleoperating with the leader arm)
- Consistent strategy for which piece to pick: **always pick the margin piece closest to the target box** (for returns: the piece nearest the margin). Consistent choices = much easier for ACT to learn.
- Record ~50 episodes per skill to start (more if success < 80%). Vary piece types, colours and which margin spots are filled; vary how many pieces are already in the boxes (0–6).
- Each episode: start at home → grasp → place → return to home. Keep episode length consistent (~10–15 s).
- Same lighting, same camera positions, same board as game-time. Don't move the overhead camera after recording.
- Place pieces well inside the box (not on the tape) so counting is unambiguous.

### Commands (verify against the installed `lerobot` version first — CLI names changed across versions; newer versions use `lerobot-find-port`, `lerobot-find-cameras`, `lerobot-calibrate`, `lerobot-teleoperate`, `lerobot-record`, `lerobot-train`)
- Find ports (`/dev/tty.usbmodem…`) and camera indices; calibrate leader and follower.
- Teleoperate with both cameras to check framing.
- Record one dataset per skill with task strings as above, cameras named `overhead` and `wrist`.
- Train on a cloud GPU (Colab/cloud) — training ACT on a Mac is slow. Inference on Mac (MPS or CPU) is fine for ACT.
- Document every exact command used in `training/README.md`.

### macOS notes
- Grant camera permission to the terminal/IDE running the app.
- Camera indices can change when USB devices are re-plugged — select cameras by name/unique ID in `config.yaml` if possible and verify at startup (show a clear error screen if a camera is missing).
- Keep the robot and cameras on a powered USB hub.

---

## 5. Vision pipeline (overhead camera)

### Calibration (`scripts/calibrate_board.py`)
- User clicks the 4 outer corners of the taped two-box rectangle and the 4 corners of the black mat on a captured frame.
- Compute a homography to a top-down "board" image. Define ROIs in board coordinates: `LEFT_BOX`, `RIGHT_BOX` (inset a few px from tape), `MARGIN` (a band around the boxes), `MAT`.
- Save to `config.yaml`. Re-run whenever the camera moves.

### Counting pieces in boxes (white background)
Start with classical CV (fast, no training):
1. HSV threshold for saturated colours (pieces are strongly coloured; table and tape are white/pale purple — exclude the tape hue).
2. Morphological open/close, find contours, filter by area.
3. Count per ROI. Optional: classify shape via polygon approximation (3 vertices = triangle, 4 = rectangle, circle = standing cylinder) for display/logging only.
4. Handle touching pieces: split large blobs using area ÷ typical piece area, or distance-transform + watershed.

### Counting answer bars (dark mat)
- Bars are bright colours on a dark background → threshold on saturation/value within `MAT` ROI.
- Bars lying side-by-side touching is the hard case (see photo: they're packed together). Approaches in order:
  1. Ask children (via GUI instruction + mat graphic) to lay bars with small gaps — easiest.
  2. Split merged blobs by width: bar width is known, count = round(blob minor-axis width / bar width).
  3. Colour-edge splitting (adjacent bars often differ in colour).
- If classical CV isn't ≥ 95% accurate on test photos, train a small YOLO (Ultralytics) detector with ~200 labelled overhead frames (classes: `piece`, `bar`, `hand`).

### Hand detection over mat
- Use MediaPipe Hands on the overhead frame; a hand counts as "over the mat" if any landmark falls inside the `MAT` ROI.
- Backup: motion/foreground detection in the `MAT` ROI (frame differencing vs. last stable frame) — a hand/arm causes large change.
- Also ignore the robot arm (it should never be over the mat, but mask its home area just in case).

### Stability & smoothing
- Run counting at ~10 fps on a background thread; keep a rolling window; a count is "stable" when the mode is unchanged for `COUNT_STABLE_SECONDS`.
- Expose a `BoardState` dataclass: `left, right, margin, bars, hand_on_mat, timestamp, stable`.

### Evaluation set
- Capture ≥ 100 overhead frames with known counts (varying piece arrangements, bars touching/not, hands present/absent). Store under `data/vision_eval/` with labels in a CSV. Report accuracy per ROI.

---

## 6. GUI

- **Framework: PySide6** (runs natively on macOS, easy threading with signals, can show camera previews).
- Child-friendly: large rounded buttons, big numbers, bright colours matching the pieces (red/blue/green/yellow), simple friendly mascot or robot icon, short sentences.
- Optional text-to-speech via macOS `say` command for instructions and feedback ("Three plus two… put your answer on the mat!").
- Optional sounds for correct/incorrect (gentle, never harsh for wrong answers).
- Full-screen mode for the demo; `Esc` shows the facilitator menu rather than quitting.
- Feedback visual: after marking, show the counted bars (e.g. "You put 4 bars") and the correct answer with dots/blocks so the child can see the difference.

---

## 7. Build phases & acceptance criteria

### Phase 1 — Skeleton + GUI + mock robot + mock vision
- Project structure, `config.yaml`, PySide6 app with Start → Round → End flow, state machine, 10 rounds, scoring, Play again / Exit / Quit.
- `MockRobotController` (sleeps ~1 s per piece) and `MockVision` (keyboard-driven: type the bar count, toggle "hand on mat").
- Unit tests for `problems.py` (constraints always hold, answers 1..10) and for the submit logic (hand seen → hand gone 2 s → stable count → submit).
- **Accept:** full 10-round game playable on the Mac with no hardware.

### Phase 2 — Cameras + calibration
- `CameraManager` opening `overhead` and `wrist` by config, threaded, with a startup check screen.
- `calibrate_board.py` producing homography + ROIs; debug overlay window showing ROIs on live video.
- **Accept:** ROIs line up with the tape boxes and mat on the live feed.

### Phase 3 — Real vision
- Piece counter, bar counter, hand detector, `BoardState` stream; `test_counter.py` live overlay.
- Build evaluation set, report accuracy.
- Swap `MockVision` for real vision in the game (robot still mocked: a human places pieces when prompted).
- **Accept:** ≥ 95% count accuracy on eval set; answer submission triggers correctly with a real hand; full game playable with a human acting as the robot.

### Phase 4 — Robot skills (parallel with Phase 3)
- Calibrate arms, verify teleoperation, record datasets for `place_left`, `place_right` (required), `return_left`, `return_right` (stretch — see §4).
- Train ACT per skill; evaluate each: 20 trials, record success rate.
- `LeRobotController` running policies in a worker thread with timeout, home-pose check, and overhead-count verification + retry.
- **Required accept:** `place_left` and `place_right` each ≥ 80% single-attempt success, ≥ 95% with one retry.
- **Stretch accept:** `return_left` and `return_right` each at the same bar. If not met by end of day, use a manual/scripted box reset between rounds for the demo instead (§4 fallback).

### Phase 5 — Integration
- Real robot + real vision in the game; delta-based reset between rounds; facilitator hotkeys; emergency stop.
- Log every round to `logs/games.csv` (problem, intended counts, verified counts, child answer, correct, robot retries, timings).
- **Accept:** 3 complete 10-round games in a row without facilitator intervention (hotkeys allowed for testing only).

### Phase 6 — Polish & demo
- TTS, sounds, animations, full-screen, mascot, clear error screens (camera missing, robot not connected).
- Metrics slide data from logs: robot placement success rate, vision accuracy, average round time, child score.

---

## 8. Safety
- Arm speed/torque limited during play; arm never enters the mat area (learner zone). Demonstrations must respect this.
- Child must not reach into the boxes while the robot is moving: GUI shows "Robot is working — hands off!" during `ROUND_SETUP`/`ROUND_RESET`; if a hand is detected in the box area during motion, pause the policy.
- Emergency stop hotkey and a physical power switch within reach of the facilitator.
- Small pieces are a choking hazard for very young children — adult supervision required.

---

## 9. Open questions / assumptions (confirm before or during Phase 1)
1. Arm model: assumed SO-101 (same flow works for SO-100 — set `robot.type` accordingly).
2. Operation is shown on screen (and spoken), not placed physically by the robot. Stretch goal: the robot places an operator tile (+ − ×) between the boxes.
3. "Exit" on the end screen returns to the Start page; the Start page has Quit to close the app.
4. Who clears the answer bars between rounds? Assumed the child, prompted by the GUI.
5. Zero as an answer (e.g. 3 − 3) is excluded for now, since an empty mat can't be "submitted".
6. (2026-09-23) This is a 1-day hackathon build requiring a demonstrated learned policy. Locked robot-model decision: ACT, scoped to `place_left`/`place_right` as required and `return_left`/`return_right` as stretch (see §4). Confirmed available: cloud GPU on standby for training plus a Mac for dev/inference, and the physical rig (arms + cameras) already assembled and ready to record data.
