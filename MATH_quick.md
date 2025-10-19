# Math Primer for Logos-Q1

This system applies applied statistics, not abstract math — but understanding the formulas helps you trust your signals.

---

## 1. Moving Averages
**Simple Moving Average (SMA):**
\[
SMA_t = \frac{1}{N} \sum_{i=0}^{N-1} Price_{t-i}
\]

Used for trend and smoothing.

---

## 2. Standard Deviation & Z-Score
**Standard Deviation:**
\[
σ_t = \sqrt{\frac{1}{N}\sum_{i=0}^{N-1}(Price_{t-i} - SMA_t)^2}
\]

**Z-Score:**
\[
z_t = \frac{Price_t - SMA_t}{σ_t}
\]
Tells how many standard deviations current price is from the mean.

---

## 3. Correlation & Pairs Trading
**Correlation (ρ):**
\[
ρ_{A,B} = \frac{Cov(A,B)}{σ_A σ_B}
\]
Measures co-movement between assets.  
High (ρ > 0.8) = they move together.

**Hedge Ratio (β):**
Estimated via linear regression:
\[
A = α + βB + ε
\]
We short/long in ratio β:1 to neutralize exposure.

---

## 4. Sharpe Ratio
\[
Sharpe = \frac{E[R - R_f]}{σ_R}
\]
Compares reward vs. volatility.  
A Sharpe > 1.0 means returns exceed noise.

---

## 5. CAGR (Compound Annual Growth Rate)
\[
CAGR = ( \frac{V_{end}}{V_{start}} )^{1/T} - 1
\]
Where T = years.

---

## 6. Max Drawdown
\[
MDD = \frac{Min(Equity)}{Max(Equity_{prior})} - 1
\]
Shows biggest capital drop; smaller is safer.

---

## 7. Exposure
\[
Exposure = \frac{TimeInMarket}{TotalTime}
\]

---

## 8. Regression & Mean Reversion
In pairs trading, spread follows roughly:
\[
Spread_t = α + ρ Spread_{t-1} + ε_t
\]
If |ρ| < 1, spread tends to revert — that’s the core of mean reversion.

---

## 9. Slippage in Basis Points
1 basis point (bps) = 0.01%.  
Slippage model:
\[
Price_{fill} = Price_{signal} × (1 + Side × \frac{bps}{10,000})
\]

---

## 10. Discrete Position Sizing
Shares per trade:
\[
Shares = \text{floor}\left(\frac{DollarPerTrade}{Price}\right)
\]

---

Together, these pieces explain how your code connects data → math → strategy → simulated profit.
