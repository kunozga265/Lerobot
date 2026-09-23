import pytest
import yaml

import scripts.calibrate_board as calibrate_board
from scripts.calibrate_board import (
    BOARD_HEIGHT,
    BOARD_WIDTH,
    BOX_HEIGHT,
    BOX_INSET,
    BOX_WIDTH,
    LEFT_BOX_DST,
    PAD_X,
    PAD_Y,
    REPROJECTION_ERROR_LIMIT_PX,
    RIGHT_BOX_DST,
    RIGHT_BOX_X,
    _cyclic_variants,
    compute_homography,
    compute_rois,
    reprojection_error_px,
    resolve_click_order,
)

# Synthetic "camera pixel" corners, generated FROM the real destination constants by a
# known scale+translate (no perspective distortion), so the 8 points are guaranteed
# consistent with a single recoverable transform rather than picked by hand and hoped
# to be consistent. The scale/offset is deliberately unrelated to any of the
# destination rectangles' own coordinates, so this exercises a "camera view" that
# doesn't coincide with board space by accident.
_SCALE_X, _SCALE_Y = 2.5, 3.0
_OFFSET_X, _OFFSET_Y = 500, 800


def _to_camera_px(dst_point: tuple[float, float]) -> tuple[float, float]:
    dx, dy = dst_point
    return _OFFSET_X + dx / _SCALE_X, _OFFSET_Y + dy / _SCALE_Y


LEFT_BOX_CORNERS = [_to_camera_px(p) for p in LEFT_BOX_DST]
RIGHT_BOX_CORNERS = [_to_camera_px(p) for p in RIGHT_BOX_DST]
MAT_CAMERA_CORNERS = [(1900, 700), (2400, 700), (2400, 950), (1900, 950)]  # arbitrary, unrelated to board space


def test_homography_maps_box_corners_onto_their_destinations():
    clicked = {"left_box": LEFT_BOX_CORNERS, "right_box": RIGHT_BOX_CORNERS}
    h = compute_homography(clicked)

    for src, expected in zip(LEFT_BOX_CORNERS + RIGHT_BOX_CORNERS, LEFT_BOX_DST + RIGHT_BOX_DST):
        x, y, w = h @ [src[0], src[1], 1]
        assert (x / w, y / w) == pytest.approx(expected, abs=0.5)


def test_reprojection_error_low_for_consistently_wound_clicks():
    clicked = {"left_box": LEFT_BOX_CORNERS, "right_box": RIGHT_BOX_CORNERS}
    h = compute_homography(clicked)
    assert reprojection_error_px(h, clicked) < 1.0


def test_reprojection_error_high_when_one_shape_wound_oppositely_and_used_as_is():
    # Documents the actual bug this tool hit: right_box's corners clicked starting
    # from a different on-screen corner / going the opposite way around from
    # left_box. That's a locally-valid rectangle for right_box alone, but globally
    # inconsistent, and produces a badly twisted homography if used as-is (i.e.
    # without resolve_click_order - see the tests below for the actual fix).
    clicked = {"left_box": LEFT_BOX_CORNERS, "right_box": list(reversed(RIGHT_BOX_CORNERS))}
    h = compute_homography(clicked)
    assert reprojection_error_px(h, clicked) > REPROJECTION_ERROR_LIMIT_PX


def test_cyclic_variants_returns_8_rotations_and_reflections():
    points = [(0, 0), (1, 0), (1, 1), (0, 1)]
    variants = _cyclic_variants(points)
    assert len(variants) == 8
    assert variants[0] == points  # first variant is the identity ordering
    assert len({tuple(v) for v in variants}) == 8  # all 8 distinct as orderings
    for variant in variants:
        assert sorted(variant) == sorted(points)  # same 4 points, just reordered


def test_resolve_click_order_recovers_a_good_fit_regardless_of_per_shape_winding():
    # The exact regression case for the bug: right_box wound opposite to left_box.
    # Unlike test_reprojection_error_high_when_one_shape_wound_oppositely_and_used_as_is,
    # resolve_click_order should find an ordering that fits well anyway.
    awkward_clicked = {"left_box": LEFT_BOX_CORNERS, "right_box": list(reversed(RIGHT_BOX_CORNERS))}

    resolved = resolve_click_order(awkward_clicked)
    h = compute_homography(resolved)

    assert reprojection_error_px(h, resolved) < 1.0
    for name in ("left_box", "right_box"):
        assert sorted(resolved[name]) == sorted(awkward_clicked[name])  # same points, just reordered


def test_compute_rois_left_and_right_box_dont_overlap_and_are_inset_from_tape():
    rois = compute_rois(MAT_CAMERA_CORNERS)

    left = rois["left_box"]
    right = rois["right_box"]
    assert left == [PAD_X + BOX_INSET, PAD_Y + BOX_INSET, PAD_X + BOX_WIDTH - BOX_INSET, PAD_Y + BOX_HEIGHT - BOX_INSET]
    assert right == [
        RIGHT_BOX_X + BOX_INSET,
        PAD_Y + BOX_INSET,
        RIGHT_BOX_X + BOX_WIDTH - BOX_INSET,
        PAD_Y + BOX_HEIGHT - BOX_INSET,
    ]
    assert left[2] < right[0]  # no overlap between the two boxes


def test_compute_rois_mat_is_stored_as_raw_camera_pixels_unwarped():
    # The mat deliberately isn't warped through the box homography (see module
    # docstring: it's not assumed coplanar with the box tape), so its ROI should be
    # exactly the clicked points, just rounded - not anything derived from board space.
    rois = compute_rois(MAT_CAMERA_CORNERS)
    assert rois["mat_camera_px"] == [list(p) for p in MAT_CAMERA_CORNERS]


def test_compute_rois_margin_is_the_full_board_canvas():
    rois = compute_rois(MAT_CAMERA_CORNERS)
    assert rois["margin"] == [0, 0, BOARD_WIDTH, BOARD_HEIGHT]


def test_write_vision_config_replaces_only_the_vision_block(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "# a helpful header comment\n"
        "game:\n"
        "  rounds_per_game: 10\n"
        "\n"
        "vision:\n"
        "  homography: null\n"
        "  rois: { left_box: null }\n"
    )
    monkeypatch.setattr(calibrate_board, "CONFIG_PATH", config_path)

    calibrate_board._write_vision_config({"board_width": 1200, "rois": {"left_box": [1, 2, 3, 4]}})

    new_text = config_path.read_text()
    assert new_text.startswith("# a helpful header comment\ngame:\n  rounds_per_game: 10\n\n")

    parsed = yaml.safe_load(new_text)
    assert parsed["game"]["rounds_per_game"] == 10  # untouched
    assert parsed["vision"] == {"board_width": 1200, "rois": {"left_box": [1, 2, 3, 4]}}
