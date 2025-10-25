# src/strategies/__init__.py
# =============================================================================
# Purpose:
#   Strategy registry for the CLI. Maps strategy names to their implementation
#   functions so users can choose strategies by string name.
#
# How to extend:
#   - Create a new file in this package with a `generate_signals(df, **params)`
#   - Import and register it below.
# =============================================================================
from typing import Any, Callable, Dict

import pandas as pd

from .mean_reversion import generate_signals as mean_reversion
from .mean_reversion import explain as mean_reversion_explain
from .momentum import generate_signals as momentum
from .momentum import explain as momentum_explain
from .carry import generate_signals as carry
from .carry import explain as carry_explain
from .pairs_trading import generate_signals as pairs_trading

StrategyGenerator = Callable[..., pd.Series]
StrategyExplainer = Callable[..., Dict[str, Any]]

STRATEGIES: Dict[str, StrategyGenerator] = {
    "mean_reversion": mean_reversion,
    "momentum": momentum,
    "carry": carry,
    "pairs_trading": pairs_trading,
}

STRATEGY_EXPLAINERS: Dict[str, StrategyExplainer] = {
    "mean_reversion": mean_reversion_explain,
    "momentum": momentum_explain,
    "carry": carry_explain,
}
