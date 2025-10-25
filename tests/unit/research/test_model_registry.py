from __future__ import annotations

import json

import pytest

from logos.research.registry import ModelRegistry


@pytest.fixture
def registry_path(tmp_path):
    return tmp_path / "registry.json"


def _mock_metrics(sharpe: float, drawdown: float) -> dict[str, float]:
    return {"Sharpe": sharpe, "MaxDD": drawdown}


def test_model_registry_promotion_flow(registry_path) -> None:
    registry = ModelRegistry(registry_path)

    candidate = registry.add_candidate(
        strategy="momentum",
        symbol="DEMO",
        params={"fast": 10, "slow": 50},
        metrics=_mock_metrics(0.8, -0.2),
        guard_metrics={"psr": 0.9},
        stress_metrics={"CAGR": 0.05},
        note="initial run",
        data_hash="data-v1",
        code_hash="code-v1",
    )
    assert candidate.status == "candidate"

    registry.promote(candidate.model_id, min_oos_sharpe=0.5, max_oos_drawdown=-0.5)
    champion = registry.champion()
    assert champion is not None
    assert champion.model_id == candidate.model_id
    assert champion.status == "champion"

    weak = registry.add_candidate(
        strategy="momentum",
        symbol="DEMO",
        params={"fast": 5, "slow": 40},
        metrics=_mock_metrics(0.1, -0.9),
        guard_metrics={"psr": 0.1},
        stress_metrics={"CAGR": -0.05},
    )

    with pytest.raises(ValueError):
        registry.promote(weak.model_id, min_oos_sharpe=0.5, max_oos_drawdown=-0.5)

    challenger = registry.add_candidate(
        strategy="momentum",
        symbol="DEMO",
        params={"fast": 12, "slow": 45},
        metrics=_mock_metrics(1.2, -0.3),
        guard_metrics={"psr": 0.95},
        stress_metrics={"CAGR": 0.08},
    )
    registry.promote(challenger.model_id, min_oos_sharpe=0.5, max_oos_drawdown=-0.5)

    archived = registry.list(status="archived")
    assert any(model.model_id == candidate.model_id for model in archived)
    assert registry.champion().model_id == challenger.model_id  # type: ignore[union-attr]

    # Ensure persistence round-trip
    fresh = ModelRegistry(registry_path)
    snapshot = fresh.list()
    assert len(snapshot) == 3
    assert fresh.champion() is not None
    payload = json.loads(registry_path.read_text())
    assert "models" in payload
