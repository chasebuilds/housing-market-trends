# Benchmark: recovering planted trends

Seed 42, 4 invented markets, 60 months, 16,069 listings. Each window is the trailing 12 months ending at the month shown. Error = estimated annual change minus the planted annual change, in percentage points (pp). Band = 95% interval from the estimator.

| Market | Method | Windows | MAE (pp) | Bias (pp) | Truth inside 95% band |
|---|---|---|---|---|---|
| Lakeshore Bend | hedonic | 49 | 1.76 | +0.09 | 96% |
| Lakeshore Bend | paired | 49 | 0.62 | +0.25 | 88% |
| Maple Ridge | hedonic | 49 | 1.66 | +0.25 | 96% |
| Maple Ridge | paired | 49 | 0.94 | +0.04 | 82% |
| Pine Hollow | hedonic | 49 | 1.72 | +0.47 | 90% |
| Pine Hollow | paired | 49 | 4.29 | +3.95 | 41% |
| Stonebrook | hedonic | 49 | 1.06 | +0.02 | 100% |
| Stonebrook | paired | 49 | 0.39 | -0.27 | 96% |
| **All markets** | hedonic | 196 | 1.55 | +0.21 | 95% |
| **All markets** | paired | 196 | 1.56 | +0.99 | 77% |

Market-condition label matches the planted direction in 176 of 196 market-months (90%).

Pine Hollow turns from +10% to -6% at month 30 (2023-07). Hedonic estimate vs planted truth, last month of each half-year around the turn:

| Month | Planted | Hedonic estimate |
|---|---|---|
| 2023-06 | +10.0% | +11.2% |
| 2023-09 | +7.2% | +10.3% |
| 2023-12 | +3.0% | +0.8% |
| 2024-03 | -0.9% | -1.6% |
| 2024-06 | -4.8% | -4.2% |
| 2024-09 | -6.0% | -5.2% |


Time regression inside each price band (all markets pooled). Cutting a band on sale price truncates the thing being modeled, so a bias is expected:

| Band | Windows | MAE (pp) | Bias (pp) | Truth inside 95% band |
|---|---|---|---|---|
| $150k-$250k | 196 | 2.94 | -0.36 | 83% |
| $250k-$400k | 147 | 3.24 | -0.49 | 63% |
| $400k+ | 124 | 3.38 | -0.41 | 90% |
| Under $150k | 59 | 1.93 | +0.28 | 100% |

Trailing windows lag a turn: a 12-month window still holds months from before the turn. Paired resales lag more, because a pair spans the whole gap between its two sales.
