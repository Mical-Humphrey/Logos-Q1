
---
# 💰 `FINANCE.md` — *Financial Concepts Explained*

```markdown
# Finance Primer for Logos-Q1

This project demonstrates the mechanics of **systematic trading** — where algorithms make decisions based on historical data.

---

## 1. Market Data
- **Price:** traded value per share at each timestamp.
- **OHLCV:** Open, High, Low, Close, Volume — used in candlestick data.
- **VWAP (Volume-Weighted Average Price):** average price weighted by traded volume.
  Traders compare their fills vs. VWAP to measure execution quality.

---

## 2. Trading Strategies

### Mean Reversion
Markets often **overreact**. If price falls too fast, it might “revert” upward.
- Compute a rolling mean and std dev.
- Measure distance (z-score).
- Buy low (z < -2), sell high (z > +2).

### Momentum
Trends persist. “The trend is your friend.”
- Compare two moving averages (fast vs. slow).
- When fast > slow, go long (uptrend); when fast < slow, go short.

### Pairs Trading
Two correlated assets (like Coke/Pepsi, MSFT/AAPL):
- Compute **spread = A - βB**, where β ≈ regression slope.
- Track its z-score.
- Long the undervalued leg, short the overvalued one.

---

## 3. Performance Metrics

| Metric | Definition |
|--------|-------------|
| **CAGR** | Compound Annual Growth Rate; long-term geometric return. |
| **Sharpe Ratio** | (Mean Return − Risk-Free Rate) / Std Dev of Returns. |
| **Max Drawdown** | Biggest peak-to-trough decline; measures downside risk. |
| **Win Rate** | % of trades closed profitably. |
| **Exposure** | Fraction of time spent “in the market.” |

---

## 4. Market Frictions

| Concept | Explanation |
|----------|--------------|
| **Slippage** | Difference between intended and executed price (latency, liquidity). |
| **Commission** | Fixed per-share fee from the broker. |
| **Spread** | Bid-ask gap; tighter spreads mean more efficient markets. |
| **Alpha** | Return generated **beyond** market movement. |
| **Beta** | Sensitivity to the overall market index. |

---

## 5. Risk Management

Real traders constrain:
- Position size (e.g., $10k per trade)
- Leverage
- Sector exposure
- Max drawdown limits
- Correlation across trades

Backtesting allows you to simulate these safely before risking capital.
