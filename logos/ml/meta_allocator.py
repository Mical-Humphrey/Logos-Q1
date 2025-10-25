from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Dict, Iterable, Optional


@dataclass(frozen=True)
class MetaAllocatorConfig:
    shrinkage: float = 0.5
    max_active_weight: float = 0.1
    cooldown_days: int = 5
    min_score: float = 0.05


@dataclass(frozen=True)
class MetaAllocationProposal:
    baseline: Dict[str, float]
    weights: Dict[str, float]
    active_weights: Dict[str, float]
    requires_approval: bool
    rationale: Iterable[str]
    approved_by: Optional[str] = None
    as_of: Optional[datetime] = None


class MetaAllocator:
    """Generates slow-moving allocation proposals gated by human approval."""

    def __init__(self, config: MetaAllocatorConfig | None = None) -> None:
        self.config = config or MetaAllocatorConfig()
        self._last_promoted: Dict[str, datetime] = {}

    def propose(
        self,
        baseline: Dict[str, float],
        advisor_scores: Dict[str, float],
        *,
        as_of: datetime,
    ) -> MetaAllocationProposal:
        if not baseline:
            raise ValueError("baseline weights required for meta allocation")
        messages = []
        adjusted = dict(baseline)
        active: Dict[str, float] = {}
        total = sum(baseline.values())
        if total <= 0:
            raise ValueError("baseline weights must sum to a positive value")

        for strategy, weight in baseline.items():
            score = advisor_scores.get(strategy, 0.0)
            if abs(score) < self.config.min_score:
                active_delta = 0.0
                messages.append(f"{strategy}: score {score:.3f} below min_score")
            else:
                cooldown_until = self._last_promoted.get(strategy)
                if cooldown_until and as_of - cooldown_until < timedelta(
                    days=self.config.cooldown_days
                ):
                    active_delta = 0.0
                    remaining = timedelta(days=self.config.cooldown_days) - (
                        as_of - cooldown_until
                    )
                    messages.append(
                        f"{strategy}: cooldown active ({remaining.days}d remaining)"
                    )
                else:
                    active_delta = self.config.shrinkage * score
            active_delta = max(
                min(active_delta, self.config.max_active_weight),
                -self.config.max_active_weight,
            )
            active[strategy] = active_delta
            adjusted[strategy] = max(weight + active_delta, 0.0)

        scale = sum(adjusted.values())
        if scale == 0:
            raise ValueError("adjusted weights collapsed to zero; check inputs")
        for strategy in adjusted:
            adjusted[strategy] /= scale

        messages.append("proposal requires human approval before promotion")
        return MetaAllocationProposal(
            baseline=dict(baseline),
            weights=adjusted,
            active_weights=active,
            requires_approval=True,
            rationale=tuple(messages),
        )

    def promote(
        self,
        proposal: MetaAllocationProposal,
        *,
        approved_by: str,
        as_of: datetime,
    ) -> MetaAllocationProposal:
        if not approved_by:
            raise ValueError("approved_by must be provided")
        for strategy in proposal.weights:
            self._last_promoted[strategy] = as_of
        return replace(
            proposal,
            requires_approval=False,
            approved_by=approved_by,
            as_of=as_of,
        )

    def last_promoted_at(self, strategy: str) -> Optional[datetime]:
        return self._last_promoted.get(strategy)
