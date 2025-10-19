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
from .mean_reversion import generate_signals as mean_reversion
from .momentum import generate_signals as momentum
from .pairs_trading import generate_signals as pairs_trading

STRATEGIES = {
    "mean_reversion": mean_reversion,
    "momentum": momentum,
    "pairs_trading": pairs_trading,
}
