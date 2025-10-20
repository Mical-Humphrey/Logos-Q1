# Phase 2 PR Templates

Use these templates when opening draft pull requests for LOGOS-SPEC-0002. Replace bracketed text
before marking "Ready for review".

---

## PR: spec/0002-translator-broker

```
## Summary
- [ ] Translator: [describe quantization + metadata changes]
- [ ] Paper broker: [describe deterministic fill + FIFO inventory]
- [ ] Tests: [list new/updated tests]

## Verification
- [ ] `pytest tests/live/test_metadata.py`
- [ ] `pytest tests/live/test_order_intent.py`
- [ ] `pytest tests/live/broker/test_paper_fill.py`

## Artifacts to Verify
- [ ] runs/live/sessions/<id>/orders.csv
- [ ] runs/live/sessions/<id>/trades.csv
- [ ] logos/logs/live.log (seed + guard logging)

## Constitution Checklist
- [ ] Reproducible & Deterministic by Default
- [ ] Safety First for Live Trading
- [ ] Read-Only Trading UI
- [ ] Tests & Docs for Every Feature
- [ ] Clear Artifact Paths
- [ ] Accessible & Fast Streamlit UI (N/A justification required)

## References
- Spec: LOGOS-SPEC-0002 (FR-001, FR-002, SC-001)
- Plan: docs/plans/phase-2-plan.md (Sprint A)
```

---

## PR: spec/0002-feeds-risk-state

```
## Summary
- [ ] Feeds: [cache replay + pollers]
- [ ] Risk guards: [list guard coverage]
- [ ] State persistence: [state.json/state.jsonl changes]
- [ ] Artifact writers: [bundle updates]

## Verification
- [ ] `pytest tests/live/data/test_cache_provider.py`
- [ ] `pytest tests/live/data/test_pollers.py`
- [ ] `pytest tests/live/test_risk_guards.py`
- [ ] `pytest tests/live/test_state_persistence.py`
- [ ] `pytest tests/live/test_runner_integration.py`

## Artifacts to Verify
- [ ] runs/live/sessions/<id>/state.json
- [ ] runs/live/sessions/<id>/session.md
- [ ] logos/logs/app.log

## Constitution Checklist
- [ ] Reproducible & Deterministic by Default
- [ ] Safety First for Live Trading
- [ ] Read-Only Trading UI
- [ ] Tests & Docs for Every Feature
- [ ] Clear Artifact Paths
- [ ] Accessible & Fast Streamlit UI (N/A justification required)

## References
- Spec: LOGOS-SPEC-0002 (FR-003, FR-004, FR-005, FR-006, US1-US3)
- Plan: docs/plans/phase-2-plan.md (Sprint A)
```

---

## PR: spec/0002-runner-integration

```
## Summary
- [ ] Runner wiring: [describe orchestration updates]
- [ ] Restart demo: [evidence of restart success]
- [ ] Risk rehearsals: [describe guard triggers]

## Verification
- [ ] `pytest tests/live/test_runner_integration.py`
- [ ] CLI demo: `python -m logos.live trade --paper --fixtures`
- [ ] Risk rehearsal script outputs stored in runs/live/sessions/<id>/session.md

## Artifacts to Verify
- [ ] runs/live/sessions/<id>/positions.csv
- [ ] runs/live/sessions/<id>/account.csv
- [ ] runs/live/sessions/<id>/trades.csv

## Constitution Checklist
- [ ] Reproducible & Deterministic by Default
- [ ] Safety First for Live Trading
- [ ] Read-Only Trading UI
- [ ] Tests & Docs for Every Feature
- [ ] Clear Artifact Paths
- [ ] Accessible & Fast Streamlit UI (N/A justification required)

## References
- Spec: LOGOS-SPEC-0002 (US1, US2, SC-001, SC-002)
- Plan: docs/plans/phase-2-plan.md (Sprint A/B integration)
```

---

## PR: spec/0002-adapters-docs

```
## Summary
- [ ] CCXT adapter: [dry-run validation]
- [ ] Alpaca adapter: [dry-run validation]
- [ ] Config validator: [safety toggles]
- [ ] Documentation: [README/MANUAL/LIVE-RUNBOOK]
- [ ] CI hardening: [offline defaults]

## Verification
- [ ] `pytest tests/live/adapters/test_ccxt_adapter.py`
- [ ] `pytest tests/live/adapters/test_alpaca_adapter.py`
- [ ] `pytest tests/live/test_config_validate.py`
- [ ] Offline regression suite script (attach log)

## Artifacts to Verify
- [ ] docs/README.md (live workflow section)
- [ ] docs/LIVE-RUNBOOK.md (safety checklist)
- [ ] runs/live/sessions/<id>/session.md (adapter summary)

## Constitution Checklist
- [ ] Reproducible & Deterministic by Default
- [ ] Safety First for Live Trading
- [ ] Read-Only Trading UI
- [ ] Tests & Docs for Every Feature
- [ ] Clear Artifact Paths
- [ ] Accessible & Fast Streamlit UI (N/A justification required)

## References
- Spec: LOGOS-SPEC-0002 (FR-007, FR-008, SC-003, SC-004)
- Plan: docs/plans/phase-2-plan.md (Sprint B)
```
