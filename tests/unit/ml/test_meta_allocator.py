from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from logos.ml.meta_allocator import MetaAllocator, MetaAllocatorConfig


def test_meta_allocator_generates_shrunk_proposal() -> None:
    config = MetaAllocatorConfig(
        shrinkage=0.5, max_active_weight=0.1, cooldown_days=3, min_score=0.05
    )
    allocator = MetaAllocator(config)
    baseline = {"strat_a": 0.5, "strat_b": 0.5}
    scores = {"strat_a": 0.3, "strat_b": -0.4}
    as_of = datetime(2025, 1, 1)

    proposal = allocator.propose(baseline, scores, as_of=as_of)
    assert proposal.requires_approval is True
    assert pytest.approx(sum(proposal.weights.values()), rel=1e-6) == 1.0
    assert proposal.active_weights["strat_a"] == config.max_active_weight
    assert proposal.active_weights["strat_b"] == -config.max_active_weight

    promoted = allocator.promote(proposal, approved_by="risk", as_of=as_of)
    assert promoted.requires_approval is False
    assert allocator.last_promoted_at("strat_a") == as_of

    blocked = allocator.propose(baseline, scores, as_of=as_of + timedelta(days=1))
    assert blocked.active_weights["strat_a"] == 0.0


def test_meta_allocator_rejects_empty_baseline() -> None:
    allocator = MetaAllocator()
    with pytest.raises(ValueError):
        allocator.propose({}, {}, as_of=datetime(2025, 1, 1))
