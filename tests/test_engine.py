from app.game.engine import AnswerWatcher


class FakeClock:
    def __init__(self, start: float = 0.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def make_watcher(hand_clear=2.0, count_stable=1.5):
    clock = FakeClock()
    watcher = AnswerWatcher(hand_clear_seconds=hand_clear, count_stable_seconds=count_stable, clock=clock)
    return watcher, clock


def test_no_submit_before_any_hand_seen():
    watcher, clock = make_watcher()
    assert watcher.update(bars=3, hand_on_mat=False) is False
    clock.advance(10)
    assert watcher.update(bars=3, hand_on_mat=False) is False


def test_no_submit_while_hand_still_on_mat():
    watcher, clock = make_watcher()
    watcher.update(bars=3, hand_on_mat=True)
    clock.advance(10)
    assert watcher.update(bars=3, hand_on_mat=True) is False


def test_no_submit_until_hand_clear_duration_elapses():
    watcher, clock = make_watcher(hand_clear=2.0, count_stable=1.5)
    watcher.update(bars=3, hand_on_mat=True)
    clock.advance(1.0)
    assert watcher.update(bars=3, hand_on_mat=False) is False  # hand gone only 1.0s < 2.0s


def test_no_submit_until_count_stable_duration_elapses():
    watcher, clock = make_watcher(hand_clear=2.0, count_stable=1.5)
    watcher.update(bars=3, hand_on_mat=True)
    clock.advance(0.1)
    watcher.update(bars=3, hand_on_mat=False)
    clock.advance(2.0)  # hand clear satisfied
    # bar count only just became "stable" now (changed at hand-removal time in this test setup)
    assert watcher.update(bars=4, hand_on_mat=False) is False  # count just changed
    clock.advance(1.0)
    assert watcher.update(bars=4, hand_on_mat=False) is False  # only 1.0s stable, need 1.5s


def test_submits_once_all_three_conditions_hold():
    watcher, clock = make_watcher(hand_clear=2.0, count_stable=1.5)
    watcher.update(bars=4, hand_on_mat=True)  # hand seen
    clock.advance(0.1)
    watcher.update(bars=4, hand_on_mat=False)  # hand now gone, count already stable since first sample
    clock.advance(2.0)  # hand clear for >= 2.0s
    assert watcher.update(bars=4, hand_on_mat=False) is True


def test_count_change_resets_stability_even_after_hand_clear():
    watcher, clock = make_watcher(hand_clear=2.0, count_stable=1.5)
    watcher.update(bars=4, hand_on_mat=True)
    clock.advance(2.1)
    assert watcher.update(bars=4, hand_on_mat=False) is True  # stable the whole time, submits

    watcher.reset()
    watcher.update(bars=4, hand_on_mat=True)
    clock.advance(2.1)
    watcher.update(bars=5, hand_on_mat=False)  # count changes right when hand clears
    assert watcher.update(bars=5, hand_on_mat=False) is False  # not stable long enough yet
    clock.advance(1.6)
    assert watcher.update(bars=5, hand_on_mat=False) is True


def test_hand_seen_again_after_clearing_requires_full_clear_wait_again():
    watcher, clock = make_watcher(hand_clear=2.0, count_stable=1.5)
    watcher.update(bars=4, hand_on_mat=True)
    clock.advance(2.1)
    watcher.update(bars=4, hand_on_mat=False)  # would submit next sample
    watcher.update(bars=4, hand_on_mat=True)  # hand returns to mat
    assert watcher.update(bars=4, hand_on_mat=False) is False  # must wait hand_clear_seconds again
