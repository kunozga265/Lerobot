# Integration plan: robot, camera and game working together

Written 2026-09-24. Tick items off as they're done.

## Where we are
- **Game logic is done.**
  - 5 rounds per game (2 add, 1 subtract, 2 multiply) and at most 2 pieces per box.
  - The sum comes from the robot commands: `a` × `place_left` and `b` × `place_right`, plus the operator. The boxes are never recounted.
  - Between rounds a helper puts the shapes back and presses **Enter**.
- **ACT models** for `place_left` / `place_right` are training.
- **Still mocked:** the game runs on `MockRobotController` + `MockVision`.
- **What's missing:**
  - the answer-mat camera logic
  - the real robot controller
  - putting both into the single app process (only one process can own a camera on macOS)

**Goal:** PLAN.md Phase 5, which is 3 complete 5-round games in a row on the real rig.

## To-dos, in order

### 1. Move the app to Python 3.12 (blocker for step 5)
Loading a trained policy runs `draccus.parse`, which crashes on Python 3.14. That's the same bug that broke `lerobot-calibrate`.
- [ ] `brew install python@3.12`
- [ ] Pipfile: `python_version = "3.12"`, pin `lerobot = {extras = ["feetech"], version = "==0.6.1"}`, add `opencv-python`
- [ ] `pipenv --rm && pipenv install --dev`
- [ ] Check: `pipenv run pytest` passes, the app launches, `pipenv run lerobot-find-port` runs

### 2. Test the trained models on the real arm (Phase 4 gate)
- [ ] `place_left`: 20 tries with `lerobot-record --policy.path=honestogarrido/act_place_left ...` (10 with the box empty, 10 with one piece already in). Target: at least 80% first-attempt success.
- [ ] `place_right`: the same.
- [ ] Below target: record 10–20 more episodes of the failing case with `--resume=true` and retrain.
- [ ] Write the exact record, train and eval commands and the success rates in `training/README.md`.

### 3. Answer-mat vision (Phase 3; can run alongside step 2)
- [ ] `scripts/capture_samples.py`: saves labelled overhead frames to `data/vision_eval/` (0–4 bars, touching and apart, hands on and off the mat).
- [ ] `app/vision/counter.py`: counts bars inside the calibrated `mat_camera_px` polygon using an HSV mask, contours, and splitting touching bars by width.
- [ ] `app/vision/hands.py`: MediaPipe Hands inside the mat polygon, with change detection as the backup.
- [ ] `app/vision/live_vision.py`: `LiveVision.get_state() -> BoardState` (same interface as `MockVision`). Runs about 10 fps on a thread and takes the most common count over the last second.
- [ ] `scripts/test_counter.py` (live overlay) and `scripts/eval_counter.py` (accuracy report). Target: at least 95% on bars and on hands.

### 4. Choose mock or real parts from config
- [ ] `config.yaml`: `robot.mode: mock|lerobot`, `vision.mode: mock|live`, follower port and ID (`/dev/tty.usbmodem5B610367201`, `my_awesome_follower_arm`), policy paths per box, policy fps.
- [ ] `app/gui/main_window.py`: builds the robot and vision from these settings, so every mix works: real vision + mock robot, mock vision + real robot, or both real.
- [ ] The mock keyboard panel only shows when vision is mocked.

### 5. Real robot controller: `app/robot/lerobot_ctrl.py`
- [ ] `LeRobotController` connects the SO-101 follower **without cameras** and takes frames from the shared `CameraManager`.
- [ ] Loads both ACT policies at startup. `place_to(box)` runs the matching policy at 30 Hz on the overhead and wrist frames plus joint state, for up to about 20 s, ending early once the arm is back near home.
- [ ] `return_from` isn't supported, because the helper resets. `go_home` moves to a saved home pose.
- [ ] Esc: add `stop()` to `RobotController` (a no-op in the mock). The policy loop checks it every step and turns motor torque off.
- [ ] Speed limit via the follower's `max_relative_target` (PLAN.md §8).

### 6. Camera resolution check (integration risk)
The policies saw 640×480 frames when recording. `CameraManager` opens cameras at 1920×1080, and the mat calibration is in 1080p pixels. If the camera's 640×480 mode is a **crop** rather than a resize, resizing a 1080p frame gives a different picture and the policy will fail.
- [ ] Compare one frame from the recorded dataset with one 1080p frame resized to 640×480, side by side.
- [ ] If they match: keep 1080p for the camera logic and resize for the policy. If they don't: open cameras at 640×480 and rerun `scripts/calibrate_board.py`.

### 7. Integration and safety (Phase 5)
- [ ] One process: `CameraManager` → `LiveVision` + `LeRobotController`. The robot runs on the engine's worker thread.
- [ ] During `ROUND_SETUP` the screen shows "Robot is working — hands off!".
- [ ] Startup check screens: camera missing, robot not connected.
- [ ] Test runs: real robot + mock vision → real vision + mock robot → both real.

### 8. Demo rehearsal
- [ ] 3 complete 5-round games in a row. Review `logs/games.csv` (`failed_placements`, setup and answer times).
- [ ] One-page demo run order: power on → `pipenv run python -m app.main` → helper keys (Enter shapes reset, Space force-submit, N skip, R home, Esc stop).

## Who does what
| Step | Owner |
|---|---|
| 1, 4, 5, 6 | Claude (this session) |
| 3 | GUI session |
| 2 | You, on the rig |
| 7, 8 | Everyone |

## Verification
- After every step: `pipenv run pytest` passes.
- Step 2: at least 80% per skill. Step 3: at least 95% mat accuracy.
- Step 7: all three mock/real mixes complete a game.
- Step 8: 3 games in a row with no helper intervention except Enter between rounds.
