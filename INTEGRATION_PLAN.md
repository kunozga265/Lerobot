# Integration plan: robot, camera and game working together

Written 2026-09-24. Tick items off as they're done.

## Where we are
- **Game logic is done.**
  - 3 rounds per game, 1 piece per box (every problem is "1 op 1", one of `+ - * /`) - a temporary demo simplification while only single-piece placement is reliable; raise `max_pieces_per_box` back up once the second-piece skill is solid.
  - The sum comes from the robot commands: `a` × `place_left` and `b` × `place_right`, plus the operator. The boxes are never recounted.
  - Between rounds a helper puts the shapes back and presses **Enter**.
- **ACT models** for `place_left` / `place_right` are training.
- **Real robot controller is built** (`app/robot/lerobot_ctrl.py`) and selectable with `robot.mode: lerobot`. It still needs trying on the real arm.
- **Still missing:** the answer-mat camera logic (`vision.mode: live`, step 3).
- **Defaults:** config ships with both parts on `mock`, so the game still runs with no hardware.

**Goal:** PLAN.md Phase 5, which is 3 complete 5-round games in a row on the real rig.

## To-dos, in order

### 1. Move the app to Python 3.12 (blocker for step 5)
Loading a trained policy runs `draccus.parse`, which crashes on Python 3.14. That's the same bug that broke `lerobot-calibrate`.
- [x] `brew install python@3.12`
- [x] Pipfile: `python_version = "3.12"`, pin `lerobot = {extras = ["feetech"], version = "==0.6.1"}`. Not adding `opencv-python`: lerobot already installs `opencv-python-headless`, and having both breaks `cv2`.
- [x] `pipenv --rm && pipenv install --dev`
- [x] Check: tests pass, `lerobot-calibrate` gets past argument parsing, and a saved ACT policy loads and runs on MPS (median step 10 ms).

### 2. Test the trained models on the real arm (Phase 4 gate)
- [ ] Save the home pose: `pipenv run python scripts/save_home_pose.py`
- [ ] `place_left`: `pipenv run python scripts/eval_skill.py left 20` (alternates empty box / one piece in). Target: at least 80% first-attempt success. It runs through the game's own controller, so it also checks the camera path from step 6. (In lerobot 0.6.1 policies run via `lerobot-rollout`; `lerobot-record --policy.path` is gone.)
- [ ] `place_right`: `pipenv run python scripts/eval_skill.py right 20`
- [ ] Below target: record 10–20 more episodes of the failing case with `--resume=true` and retrain.
- [x] `training/README.md` has the exact record, train and eval commands. Fill in the dataset names and success rates as they come in.

### 3. Answer-mat vision (Phase 3; can run alongside step 2)
Code is done; the thresholds still need tuning on the rig with real photos.
- [ ] **First, recalibrate the mat.** `cameras` is now 640×480 but `vision.rois.mat_camera_px` is still in 1080p pixels (x up to 1752), so live vision refuses to start. Run `pipenv run python scripts/calibrate_board.py` on the rig.
- [x] `scripts/capture_samples.py`: live preview. Keys 0–4 set the bar label, h toggles hand, space saves to `data/vision_eval/` + `labels.csv` (`data/` is git-ignored).
- [x] `app/vision/counter.py`: bars inside the mat polygon via an HSV mask (saturation and brightness), open/close cleanup, contours, and splitting touching bars by `bar_width_px`.
- [x] `app/vision/hands.py`: no model needed. It's a hand if enough of the mat is skin-coloured (YCrCb range) or changed since the last frame. MediaPipe wasn't installed (network); add it behind `HandDetector.update` only if accuracy falls short.
- [x] `app/vision/live_vision.py`: `LiveVision(cameras, config)`, 10 fps thread, the most common count over 1 s, same `get_state()` as `MockVision`. Checked end to end: a scripted camera placing 3 bars with a hand gets submitted as 3, about 1.2 s after the hand leaves.
- [x] `scripts/test_counter.py` (live overlay, sliders, `p` prints the YAML) and `scripts/eval_counter.py` (accuracy report, lists failures).
- [ ] On the rig: capture 100+ frames → tune with `test_counter.py` (lay one bar to read its width for `bar_width_px`) → paste the printed `vision.mat` / `vision.hands` into `config.yaml` → `eval_counter.py` until at least 95% for bars and hands.
- [ ] Game test: `vision.mode: live`, `robot.mode: mock`; play with real bars and hands.

### 4. Choose mock or real parts from config
- [x] `config.yaml`: `robot.mode: mock|lerobot`, `vision.mode: mock|live`, follower port and ID, policy paths, tasks and timings per box, and camera capture size.
- [x] `app/hardware.py` builds the real parts once at startup. `MainWindow` fills any gap with mocks, so every mix works.
- [x] The mock keyboard panel only shows when vision is mocked.

### 5. Real robot controller: `app/robot/lerobot_ctrl.py`
- [x] `LeRobotController` connects the SO-101 follower **without cameras** and takes frames from the shared `CameraManager` (BGR → RGB, resized to 640×480).
- [x] Loads both ACT policies at startup. `place_to(box)` runs the matching policy at 30 Hz, ending once the arm is back near home (after 3 s) or after 20 s.
- [x] `return_from` isn't supported (the helper resets). `go_home` moves to the saved home pose, off the GUI thread.
- [x] `RobotController.stop(emergency)`. Leaving a game aborts the motion; Esc also turns torque off, and the next move turns it back on.
- [x] Speed limit: `robot.max_relative_target: 15` (tune on the real arm).
- [ ] Try it on the real arm (covered by the step 2 trials).

### 6. Camera resolution check (integration risk)
The policies saw 640×480 frames when recording. `CameraManager` opens cameras at 1920×1080, and the mat calibration is in 1080p pixels. If the camera's 640×480 mode is a **crop** rather than a resize, resizing a 1080p frame gives a different picture and the policy will fail.
- [ ] `pipenv run python scripts/check_policy_frames.py honestogarrido/place_left_20260923_174813`, then open `data/policy_frame_check/*.png` and compare the two halves.
- [ ] If they match: keep 1080p for the camera logic and resize for the policy. If they don't: open cameras at 640×480 and rerun `scripts/calibrate_board.py`.

### 7. Integration and safety (Phase 5)
- [x] One process: `CameraManager` → `LiveVision` + `LeRobotController`. The robot runs on the engine's worker thread.
- [x] During `ROUND_SETUP` the screen shows "Watch the robot… hands off the boxes!".
- [x] Startup check: a missing camera or an unconnected robot shows an error dialog naming the problem, and the app exits.
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
