"""Translate strategy signals into live order intents."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Deque, Dict, Iterable, List, TypedDict, cast

import pandas as pd

from logos.strategies import STRATEGIES

from .broker_base import BrokerAdapter, OrderIntent, SymbolMeta
from .data_feed import Bar
from .order_sizing import SizingConfig, TargetPosition, generate_order_intents


@dataclass
class StrategySpec:
    """Configuration describing how to size strategy signals."""

    symbol: str
    strategy: str
    params: Dict[str, float] = field(default_factory=dict)
    dollar_per_trade: float = 10_000.0
    max_bars: int = 512
    sizing: SizingConfig = field(default_factory=SizingConfig)


class RollingBar(TypedDict):
    """Pandas-friendly rolling OHLCV bar used for signal evaluation."""

    Timestamp: datetime
    Open: float
    High: float
    Low: float
    Close: float
    Volume: float


StrategyFunction = Callable[..., pd.Series]


class StrategyOrderGenerator:
    """Maintains rolling bars and converts strategy signals into orders."""

    def __init__(self, broker: BrokerAdapter, spec: StrategySpec) -> None:
        if spec.strategy not in STRATEGIES:
            raise ValueError(f"Unknown strategy '{spec.strategy}'")
        self.broker = broker
        self.spec = spec
        self.strategy_fn = cast(StrategyFunction, STRATEGIES[spec.strategy])
        self.meta: SymbolMeta = broker.get_symbol_meta(spec.symbol)
        self._bars: Deque[RollingBar] = deque(maxlen=spec.max_bars)
        self._last_target_qty: float = 0.0

    # ------------------------------------------------------------------
    def process(self, bars: Iterable[Bar], current_qty: float) -> List[OrderIntent]:
        """Update internal state with new bars and emit order intents."""

        added = False
        for bar in bars:
            self._bars.append(
                {
                    "Timestamp": bar.dt,
                    "Open": float(bar.open),
                    "High": float(bar.high),
                    "Low": float(bar.low),
                    "Close": float(bar.close),
                    "Volume": float(bar.volume),
                }
            )
            added = True
        if not added or not self._bars:
            return []

        frame = pd.DataFrame(list(self._bars)).set_index("Timestamp")
        frame = frame[~frame.index.duplicated(keep="last")].sort_index()
        if frame.empty:
            return []

        signals = (
            self.strategy_fn(frame, **self.spec.params)
            if self.spec.params
            else self.strategy_fn(frame)
        )
        if signals.empty:
            return []

        latest_signal = signals.iloc[-1]
        if pd.isna(latest_signal):
            latest_signal = 0
        latest_signal = int(latest_signal)

        price = float(frame.iloc[-1]["Close"])
        if price <= 0:
            return []

        target_qty = (latest_signal * self.spec.dollar_per_trade) / price
        if self.spec.sizing.max_position > 0:
            cap = self.spec.sizing.max_position
            target_qty = max(min(target_qty, cap), -cap)

        if (
            abs(target_qty - current_qty) < 1e-6
            and abs(target_qty - self._last_target_qty) < 1e-6
        ):
            return []

        target = TargetPosition(symbol=self.spec.symbol, quantity=target_qty)
        intents = generate_order_intents(
            current_qty=current_qty,
            target=target,
            price=price,
            meta=self.meta,
            sizing=self.spec.sizing,
        )
        if intents:
            self._last_target_qty = target_qty
        return intents
