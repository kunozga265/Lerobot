# Training record: place_left / place_right (ACT)

The exact commands used for the robot skills (PLAN.md §4). **Update this whenever a command or dataset changes.**

lerobot **0.6.1** on **Python 3.12**. Python 3.14 breaks lerobot's config parser (`draccus`).

## Hardware
| | Port | ID |
|---|---|---|
| Leader | `/dev/tty.usbmodem5B3D0426861` | `my_awesome_leader_arm` |
| Follower | `/dev/tty.usbmodem5B610367201` | `my_awesome_follower_arm` |

- **Cameras** (on the dev Mac): `overhead` = index 1, `wrist` = index 0. They may differ on another Mac; check with `lerobot-find-cameras opencv`.
- **Calibration files** are in `~/.cache/huggingface/lerobot/calibration/`. Copy the folder to any other Mac and keep the same IDs.

## Calibrate
```bash
lerobot-calibrate --robot.type=so101_follower --robot.port=/dev/tty.usbmodem5B610367201 --robot.id=my_awesome_follower_arm
lerobot-calibrate --teleop.type=so101_leader --teleop.port=/dev/tty.usbmodem5B3D0426861 --teleop.id=my_awesome_leader_arm
```

## Record
Each side has 2 margin spots and 2 box spots. Mix two variants in one dataset:
- **Variant A:** box empty → place the first piece.
- **Variant B:** one piece already in → place the second.

Always pick the spot closer to the box first, and swap which shape sits on which spot between episodes. Every episode starts and ends at home.
```bash
lerobot-record \
  --robot.type=so101_follower --robot.port=/dev/tty.usbmodem5B610367201 --robot.id=my_awesome_follower_arm \
  --robot.cameras="{overhead: {type: opencv, index_or_path: 1, width: 640, height: 480, fps: 30}, wrist: {type: opencv, index_or_path: 0, width: 640, height: 480, fps: 30}}" \
  --teleop.type=so101_leader --teleop.port=/dev/tty.usbmodem5B3D0426861 --teleop.id=my_awesome_leader_arm \
  --display_data=true \
  --dataset.repo_id=honestogarrido/place_left_20260923_174813 \
  --dataset.single_task="Pick a piece from the margin and place it in the left box" \
  --dataset.num_episodes=50 --dataset.episode_time_s=15 --dataset.reset_time_s=10 \
  --dataset.push_to_hub=true
```
- **`place_right`:** the same command with its own `repo_id` and the task `"Pick a piece from the margin and place it in the right box"`.
- **Adding episodes:** add `--resume=true` to continue an existing dataset.

| Skill | Dataset | Episodes |
|---|---|---|
| place_left | `honestogarrido/place_left_20260923_174813` | _fill in_ |
| place_right | _fill in_ | _fill in_ |

## Train (cloud GPU)
```bash
lerobot-train \
  --dataset.repo_id=honestogarrido/place_left_20260923_174813 \
  --policy.type=act \
  --policy.device=cuda \
  --policy.repo_id=honestogarrido/act_place_left \
  --output_dir=outputs/train/act_place_left_20260923_174813 \
  --job_name=act_place_left_20260923_174813 \
  --wandb.enable=false
```
- **Device:** use `--policy.device=cuda` on the cloud GPU. `mps` works on the Mac but is very slow for training.
- **Name each model after its skill** (`act_place_left`, `act_place_right`). A shared name such as `my_policy` gets overwritten.
- **Game config:** `app/config.yaml` → `robot.policies.left.path` / `right.path` must point at these `policy.repo_id`s.

## Before evaluating
1. Save the home pose. Torque turns off; move the follower to home by hand and press Enter:
   ```bash
   pipenv run python scripts/save_home_pose.py
   ```
2. Check that the game's camera frames match the training frames (INTEGRATION_PLAN.md step 6):
   ```bash
   pipenv run python scripts/check_policy_frames.py honestogarrido/place_left_20260923_174813
   ```
   Open `data/policy_frame_check/*.png`. Both halves should show the same view.

## Evaluate (target: at least 80% first-attempt success)
Run the trials through the game's own controller, alternating empty box and one-in-box. Results are appended to `training/eval_results.csv`.
```bash
pipenv run python scripts/eval_skill.py left 20
pipenv run python scripts/eval_skill.py right 20
```
Ctrl+C stops immediately with torque off.

Alternative using lerobot's own runner (no camera-path check):
```bash
lerobot-rollout --strategy.type=base \
  --policy.path=honestogarrido/act_place_left \
  --robot.type=so101_follower --robot.port=/dev/tty.usbmodem5B610367201 --robot.id=my_awesome_follower_arm \
  --robot.cameras="{overhead: {type: opencv, index_or_path: 1, width: 640, height: 480, fps: 30}, wrist: {type: opencv, index_or_path: 0, width: 640, height: 480, fps: 30}}" \
  --task="Pick a piece from the margin and place it in the left box" --duration=20
```
In lerobot 0.6.1 policies run through `lerobot-rollout`, not `lerobot-record --policy.path`.

| Skill | Model | Success (first attempt) | Date |
|---|---|---|---|
| place_left | `honestogarrido/act_place_left` | _fill in_ | |
| place_right | `honestogarrido/act_place_right` | _fill in_ | |
