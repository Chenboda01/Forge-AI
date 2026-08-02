from forge.ui.keyboard import KeyboardController


def test_escape_sequence_uses_total_elapsed_time() -> None:
    # Given: five Escape presses whose adjacent gaps fit but total duration does not
    clock = iter((0.0, 1.2, 2.4, 3.6, 4.8)).__next__
    keyboard = KeyboardController(clock=clock)

    # When: every press is recorded
    counts = [keyboard.record_escape() for _ in range(5)]

    # Then: no five-press sequence is recognized
    assert counts == [1, 2, 1, 2, 1]


def test_escape_sequence_accepts_presses_inside_total_window() -> None:
    # Given: five Escape presses completed inside one 1.25-second window
    clock = iter((10.0, 10.2, 10.4, 10.6, 10.8)).__next__
    keyboard = KeyboardController(clock=clock)

    # When / Then: the fifth press completes the sequence
    assert [keyboard.record_escape() for _ in range(5)] == [1, 2, 3, 4, 5]


def test_escape_sequence_resets_after_window_boundary() -> None:
    # Given: a second Escape press just beyond the total sequence boundary
    clock = iter((5.0, 6.250001)).__next__
    keyboard = KeyboardController(clock=clock)

    # When / Then: the later press starts a new sequence
    assert keyboard.record_escape() == 1
    assert keyboard.record_escape() == 1
