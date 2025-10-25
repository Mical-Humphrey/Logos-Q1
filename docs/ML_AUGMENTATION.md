# ML Augmentation (Phase 11)

Phase 11 adds offline, human-gated intelligence to Logos. All outputs are advisory and require explicit approval before entering live execution or allocation flows.

## Modules

| Module | Purpose |
| --- | --- |
| `logos.ml.regime.RegimeAdvisor` | Detects trend/volatility regimes from price history; returns `RegimeReport` objects with confidence metadata. Promotion requires human sign-off via `RegimeAdvisor.promote`. |
| `logos.ml.vol.VolatilityAdvisor` | Computes EWMA-based volatility envelopes and sizing guidance. Use `VolatilityAdvisor.promote` to annotate approved forecasts. |
| `logos.ml.meta_allocator.MetaAllocator` | Generates shrinkage-based allocation proposals subject to caps and cooldowns. Proposals remain `requires_approval=True` until `MetaAllocator.promote` records an approver and timestamp. |
| `logos.ml.drift` | Provides feature and PnL drift checks (Population Stability Index, z-score deltas). Reports can be merged to document advisory triggers. |

## Workflow Overview

1. **Prepare data offline** – feed cleaned price/feature series into `RegimeAdvisor` and `VolatilityAdvisor` to generate advisory signals.
2. **Generate allocation proposals** – pass baseline weights and advisor scores into `MetaAllocator.propose`. The result always requires a human approver.
3. **Review drift monitors** – use `detect_feature_drift` and `detect_pnl_drift` to catch regime breaks. Merge reports to create escalation packages for risk reviews.
4. **Promote only after approval** – the `promote` helpers enforce a non-empty `approved_by` identity, preventing accidental automation.

## Promotion Gates

- Maintain an approval log (e.g., in run metadata) referencing the `approved_by` values stamped onto promoted reports/proposals.
- Couple promotions with paper A/B evidence: combine advisory outputs with existing backtests before any live rollout.
- Reset cooldowns in `MetaAllocatorConfig` when significant structural changes occur; re-run drift analysis before resuming promotions.

## Testing & Validation

- Unit tests reside in `tests/unit/ml/` and execute in < 7 minutes on commodity hardware to respect FR-003.
- For offline validation, compare A/B walk-forward metrics before and after advisory adjustments. Only promote if improvement persists out of sample.

## Residual Risks

- Heuristic thresholds (trend, PSI, z-score) require periodic recalibration. Record adjustments in change management notes.
- Advisory components run offline; ensure data lineage captures the dataset version for reproducibility when presenting to risk/governance.
