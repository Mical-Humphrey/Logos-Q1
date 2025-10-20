Test Design and Coverage Overview for Logos-Q1

Purpose
This document explains how the test suites are organized, what each suite validates, and why each test is important for the quality and safety of the Logos-Q1 quantitative trading system. The tests focus on correctness of core analytics, backtesting outputs, CLI workflows, data loading and caching, tutorial flows, and live-trading scaffolding such as the paper broker and live runner.

How to Run
From the project root (Logos-Q1/), run:
    pytest
Tests are written with pytest and use fixtures and monkeypatching to isolate the filesystem, remove external dependencies (e.g., network, plotting backends), and ensure deterministic behavior.

Testing Philosophy and Patterns
- Determinism and stability: Randomness is seeded where used; numerical functions are checked for ranges and non-NaN outputs.
- Isolation: Temporary directories (tmp_path) and monkeypatching redirect I/O (data caches, logs, run artifacts) to ephemeral locations.
- No external network effects: Data downloads and live feeds are faked; CLI and subprocess invocations are constrained; plotting uses a headless backend (Agg).
- Output contract checks: Tests assert presence, structure, and basic plausibility of computed metrics, trades, and equity curves.
- Edge cases: Zero-variance returns, empty or flat signals, and parameter permutations are included to prove graceful handling.

Global Test Utilities
- tests/README.md
  What it does: Provides a minimal instruction to run the entire test suite from the repository root with pytest.
  Why it’s important: Ensures contributors have a straightforward, canonical entry point to validate changes before pushing or opening a PR. Reduces friction and supports consistent test execution across environments.

- tests/conftest.py
  What it does: Ensures the project root is on sys.path so imports like `import logos` work in tests.
  Why it’s important: Keeps tests decoupled from specific IDE or PYTHONPATH setup. Contributors can run tests uniformly without modifying environment variables or installing the package in editable mode.

Core Analytics and Utilities
- tests/test_metrics.py
  What it tests: Core performance metrics—Sharpe, Sortino, CAGR, Max Drawdown, Volatility—on synthetic return streams. Validates outputs are well-defined (not NaN), within expected ranges, and handle zero-variance inputs returning zero metrics where appropriate.
  What it proves: Numerical stability and correctness of foundational metrics used across backtesting and reporting. Prevents regressions that could invalidate strategy evaluation or risk assessment.

- tests/test_periods_per_year.py
  What it tests: The `periods_per_year` helper in the CLI layer for various asset classes (equity, crypto, forex) and intervals (daily and intraday), including aliases (e.g., fx vs forex).
  What it proves: Accurate annualization factors for different markets and timeframes—a critical prerequisite for annualized metrics (e.g., Sharpe, CAGR). Guards against subtle mistakes that would systematically bias results.

Backtesting Pipeline and CLI
- tests/test_backtest_engine_metrics.py
  What it tests: The backtest engine’s end-to-end output contract given simple synthetic prices and signals. Asserts the presence and lengths of equity curve and returns, the schema of trades, and required metrics (CAGR, Sharpe, MaxDD, WinRate, Exposure). Also verifies that flat signals produce zero exposure and Sharpe.
  What it proves: The backtest engine produces consistent, complete artifacts and metrics with correct shapes and sanity-checked ranges. It protects the public API surface of the backtester against breaking changes.

- tests/test_cli_defaults.py
  What it tests: The `cmd_backtest` command path with controlled inputs. It stubs out run creation, logging, strategy selection, pricing data, and backtest outputs to verify that run artifacts (config, metrics, trades, plots/log files) are written to the expected locations.
  What it proves: CLI-driven workflows correctly orchestrate data fetching, strategy execution, and artifact generation. This ensures users invoking the tool from the command line get stable run directories and outputs suitable for inspection and automation.

- tests/test_readme_commands.py
  What it tests: A suite of representative README-documented backtest and tutor CLI invocations. Sets the plotting backend to Agg; isolates data/cache/runs/logs to temp directories; and runs smoke checks for multiple permutations of symbols, strategies, asset classes, intervals, and parameters.
  What it proves: The documented examples remain executable and up to date. Prevents documentation drift and ensures newcomers can reproduce examples without accidental I/O or environment bleed-through.

Data Access and Caching
- tests/test_data_loader.py
  What it tests: Data loading from “raw” CSV fixtures and the behavior of cache writes for downloaded data (via a stubbed downloader). Confirms expected columns/indices and that cache files are created in the right structure and naming.
  What it proves: Deterministic, reproducible data ingestion that respects the project’s on-disk layout. Reduces runtime cost via caching, while ensuring fresh downloads integrate transparently.

Tutor Mode and Educational Flows
- tests/test_tutor_mode.py
  What it tests: A subprocess invocation of the Tutor CLI module (`python -m logos.tutor --list`) returning successfully and listing known lessons (e.g., “mean_reversion”).
  What it proves: The Tutor CLI entry point is wired and discoverable in a real process context. Validates packaging, module structure, and a minimal interactive capability.

- tests/test_tutor_engine.py
  What it tests: The internal tutor engine `run_lesson` pipeline with fake run directories, settings, prices, and backtest results. Asserts that transcript, glossary, and explanation artifacts are written and have reasonable content (e.g., non-empty glossary).
  What it proves: The education-focused runs generate all expected artifacts and are robust to content/plot toggles. Ensures a coherent learning experience with reproducible outputs.

Live Trading Scaffolding
- tests/test_paper_broker.py
  What it tests: Paper broker order lifecycle and accounting. Covers market order fills (positions, average price, cash, equity updates), limit order behavior (waits for price, caps fill price), and bootstrapping positions with pre-existing holdings and realized P&L.
  What it proves: The simulated broker’s state machine and accounting are consistent and financially correct. Fundamental for safely testing strategies without risking capital or requiring real broker connectivity.

- tests/test_live_runner.py
  What it tests: The live strategy order generation path, constructing a `StrategyOrderGenerator` and verifying emitted intents (e.g., correct side, symbol, order type, and quantity sized from dollar-per-trade and price). It also patches filesystem paths used by live sessions/runs to temporary locations.
  What it proves: The gateway between bar data and orders produces sensible, sized trade intents. This is the core control logic that would ultimately feed a broker; correctness here avoids over-sizing, wrong-sided trades, or malformed orders.

- tests/test_cached_feed.py
  What it tests: A CSV-backed cached polling feed for intraday bars. Verifies that fresh cache data is served without calling the provider; stale data triggers a provider fetch; and that serialization/deserialization of bar records is consistent with defined CSV headers.
  What it proves: Efficient, resilient live data ingestion that minimizes provider calls while ensuring recency. Critical for both cost control and timely decision-making in live or paper sessions.

Cross-Module Design Notes
- Isolation via monkeypatch: Paths for data, cache, runs, logs, and live-session directories are redirected to temporary folders in multiple tests to ensure clean state and reproducibility.
- Headless plotting: Tests enforce a non-interactive backend (Matplotlib Agg) to prevent GUI dependencies and to enable CI compatibility.
- Minimal external effects: Live systems, downloads, and subprocesses are exercised just enough to validate integration points without depending on remote services or global user environment.
- Contract-first assertions: Many tests focus on the presence and structure of key artifacts (metrics, trades, equity curves, lesson outputs), providing strong signals when a refactor would break consumers.

Extending the Suite
When adding new functionality:
- Add unit tests that pin down numerical or stateful behavior with deterministic inputs.
- Add integration tests that assert output contracts and file artifact shapes where relevant.
- Keep I/O isolated with tmp_path and monkeypatch; stub external services.
- Update README-backed smoke tests if new CLI examples or flags are documented.

Summary
Together, these tests provide strong coverage of Logos-Q1’s critical paths—numerical correctness, data handling, CLI orchestration, tutorial experiences, and live-trading scaffolding. They are designed to fail loudly on breaking changes to public behavior while remaining fast, deterministic, and CI-friendly.