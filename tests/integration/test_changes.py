from custom_components.cliproxy.changes import changes

NOW = "2026-11-07T04:00:00+00:00"


def reading(percent, resets_at, fetched_at=NOW, out_of_usage=False):
    return {
        "fetched_at": fetched_at,
        "accounts": [
            {
                "id": "a1",
                "account": "codex/pro@example.com",
                "provider": "codex",
                "out_of_usage": out_of_usage,
                "usage_back_at": None,
                "limits": [{"key": "primary", "name": "Weekly", "percent": percent, "resets_at": resets_at}],
            }
        ],
        "providers": [],
    }


def resets(before, after):
    return [data["limit"] for event, data in changes(before, after) if event == "cliproxy_usage_reset"]


def test_a_window_that_rolls_over_at_its_deadline_is_a_reset():
    before = reading(97.0, "2026-11-07T03:59:00+00:00", fetched_at="2026-11-07T03:58:00+00:00")
    after = reading(97.0, "2026-11-14T03:59:00+00:00")

    assert resets(before, after) == ["primary"]


def test_a_deadline_passing_without_a_new_reading_is_a_reset_once():
    before = reading(100.0, "2026-11-07T03:59:00+00:00", fetched_at="2026-11-07T03:58:00+00:00")
    expired = reading(0.0, None)
    fresh = reading(3.0, "2026-11-14T03:59:00+00:00", fetched_at="2026-11-07T04:01:00+00:00")

    assert resets(before, expired) == ["primary"]
    assert resets(expired, fresh) == []


def test_a_banked_reset_that_moves_the_deadline_a_little_is_a_reset():
    assert resets(reading(100.0, "2026-11-07T04:10:00+00:00"), reading(0.0, "2026-11-07T04:15:00+00:00")) == ["primary"]


def test_a_deadline_pushed_out_early_without_usage_dropping_is_not_a_reset():
    assert resets(reading(40.0, "2026-11-09T00:00:00+00:00"), reading(41.0, "2026-11-10T00:00:00+00:00")) == []


def test_a_deadline_wobbling_by_a_second_is_not_a_reset():
    assert resets(reading(10.0, "2026-11-30T04:58:29+00:00"), reading(5.0, "2026-11-30T04:58:30+00:00")) == []


def test_the_same_reading_twice_fires_nothing():
    same = reading(50.0, "2026-11-09T00:00:00+00:00")

    assert changes(same, same) == []
