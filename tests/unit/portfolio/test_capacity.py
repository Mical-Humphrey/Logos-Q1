import math

from logos.portfolio.capacity import compute_adv_notional, compute_participation


def test_compute_adv_notional_filters_non_finite_values():
    observations = [1_000_000.0, float("nan"), 800_000.0, float("inf"), 1_200_000.0]
    adv = compute_adv_notional(observations)
    assert math.isclose(adv, (1_000_000.0 + 800_000.0 + 1_200_000.0) / 3, rel_tol=1e-9)


def test_compute_participation_handles_zero_adv():
    assert compute_participation(100_000.0, 0.0) == 0.0
    assert compute_participation(100_000.0, -50_000.0) == 0.0


def test_compute_participation_returns_absolute_ratio():
    adv = 5_000_000.0
    order_notional = -200_000.0
    participation = compute_participation(order_notional, adv)
    assert math.isclose(participation, abs(order_notional) / adv, rel_tol=1e-9)
