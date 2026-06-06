---
name: portable-buy-range-plan
description: >-
  Generate beginner-friendly technical buy ranges for stocks or ETFs from free
  public market data, with optional short-term operation plans only when
  explicitly requested. Use when the user asks for a buy range, entry zone,
  dip-buy area, add zone, tactical plan, take-profit, stop, or invalidation level
  without relying on a private database, paid market data, or project-specific
  code.
---

# Portable Buy Range Plan

Use this skill to compute a simple technical buy range from free public market
data. It is designed to work in Codex or Claude Code: run the bundled Python
script and present the result in the user's language.

## Intent Routing

- If the user asks only for a buy range / entry zone / where to buy, run the
  default range-only mode and do not output a short-term operation plan.
- If the user explicitly asks for an operation plan, short-term plan,
  take-profit, stop, invalidation, or position-building steps, run `--plan`.
- Do not rename a range-only answer as a "short-term buy plan".
- Do not add 2SD/3SD, take-profit, or stop sections to a range-only answer.

## Commands

Run from this skill directory:

```powershell
python scripts\portable_buy_range_plan.py MU
python scripts\portable_buy_range_plan.py MU CLS
python scripts\portable_buy_range_plan.py TQQQ --plan
python scripts\portable_buy_range_plan.py MU --price MU=864.01
python scripts\portable_buy_range_plan.py --demo
```

From another working directory, pass the absolute path to the script:

```powershell
python C:\path\to\portable-buy-range-plan\scripts\portable_buy_range_plan.py MU
```

Default mode is range-only. `--range-only` is accepted but unnecessary.

## Data Rules

- Use free public data only.
- The script prefers `yfinance` and falls back to Stooq daily CSV.
- Use at least 120 trading days of daily prices; if unavailable, report
  unavailable instead of fabricating a range.
- If the user provides a price, pass it with `--price TICKER=PRICE` and label it
  as user-provided.
- If the script fails, surface the real error. Do not claim the script failed
  unless you actually ran it and saw the failure.

## Output Rules

For range-only requests, present:

- current price and source;
- ticker profile;
- Starter / Main add / Reserve ranges and planned percentages;
- a brief "current price vs range" read;
- a reminder that this is a technical reference, not a prediction or standalone
  buy recommendation.

For explicit plan requests, present:

- the same three buy ranges;
- step-by-step entry plan;
- two take-profit references;
- 2SD/3SD stress scenarios as risk references, not extra buy orders;
- invalidation action;
- a reminder that this is not a prediction.

## Interpretation Notes

- Starter means a small first test entry.
- Main add means the primary pullback area.
- Reserve means a deeper pullback area; use only after stabilization.
- For leveraged ETFs such as TQQQ, SOXL, UPRO, SPXL, and FNGU, always mention
  path decay and that they are tactical tools, not no-thought long-term holds.
- For volatile stocks, explain that ranges are wide and can be invalidated by
  earnings, sector news, liquidity, or company-specific shocks.
