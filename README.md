# Portable Buy Range Plan

Portable Buy Range Plan is a Codex / Claude Code skill plus a standalone Python
script for generating beginner-friendly technical buy ranges from free public
market data.

It is designed for users who want a practical answer to:

- "What is the buy range for MU?"
- "Where should I wait before buying TQQQ?"
- "Give me a short-term operation plan with entries, take-profit, and invalidation."

The default output is **buy range only**. The expanded operation plan is emitted
only when you explicitly pass `--plan`.

> This tool is not financial advice. It is a technical price-structure reference
> based on public historical prices. Always check current news, liquidity,
> earnings events, and your own risk limits before acting.

## Features

- Free public data only.
- Uses `yfinance` first, then falls back to Stooq daily CSV.
- Requires at least 120 trading days of daily prices.
- Default range-only output for simple buy-range requests.
- Optional `--plan` output with:
  - step-by-step entries,
  - two take-profit references,
  - 2SD / 3SD stress scenarios,
  - invalidation action.
- Handles high-volatility stocks and leveraged ETFs differently.
- Explicitly rejects invalid user-provided prices instead of silently falling
  back to market data.

## Repository Layout

```text
portable-buy-range-plan/
├── SKILL.md
├── README.md
├── requirements.txt
├── agents/
│   └── openai.yaml
└── scripts/
    └── portable_buy_range_plan.py
```

## Install

Clone the repository:

```bash
git clone https://github.com/sidwakewake/portable-buy-range-plan.git
cd portable-buy-range-plan
```

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

`yfinance` is optional at runtime because the script can fall back to Stooq, but
installing it gives better ticker coverage and metadata.

## Quick Start

Buy range only:

```bash
python scripts/portable_buy_range_plan.py MU
```

Multiple tickers:

```bash
python scripts/portable_buy_range_plan.py MU CLS TQQQ
```

Use a user-provided current price:

```bash
python scripts/portable_buy_range_plan.py MU --price MU=864.01
```

Expanded operation plan:

```bash
python scripts/portable_buy_range_plan.py TQQQ --plan
```

Built-in demo data:

```bash
python scripts/portable_buy_range_plan.py --demo
```

## Skill Usage In Codex Or Claude Code

Put this folder under a skills directory, for example:

```text
~/.agents/skills/portable-buy-range-plan
```

Then ask:

```text
Use portable-buy-range-plan to get MU's buy range.
```

For an explicit operation plan:

```text
Use portable-buy-range-plan to create a TQQQ short-term operation plan.
```

The skill's routing rule is intentional:

- "buy range" means range-only;
- "operation plan", "take-profit", "stop", or "invalidation" means use
  `--plan`.

## Output Modes

### Default: Buy Range Only

The default mode shows:

- current price and source;
- ticker profile;
- Starter / Main add / Reserve ranges;
- planned split percentages;
- a quick read of whether current price is above, inside, or below the range.

It does **not** show take-profit, stop, invalidation, or 2SD / 3SD sections.

### Optional: Operation Plan

`--plan` adds:

- step-by-step entry plan;
- TP1 and TP2;
- 2SD and 3SD stress scenarios;
- invalidation action;
- leveraged ETF and high-volatility warnings where applicable.

Stress scenarios are risk references, not additional buy orders.

## Model Notes

The script builds a technical anchor from moving averages and the recent
90-trading-day high. It then applies profile-specific drawdown ladders:

- broad ETF;
- steady stock;
- core stock;
- volatile stock;
- leveraged ETF.

The volatile-stock and leveraged-ETF ladders are intentionally conservative and
were calibrated against a private reference workflow for broad behavioral
parity, while remaining fully portable and free-data-only.

This repository does not include private database logic, paid data, option-chain
logic, or project-specific code.

## Examples

Range-only example:

```bash
python scripts/portable_buy_range_plan.py MU
```

Typical output sections:

```text
# Technical Buy Range

## MU Buy Range

| Zone | Buy range | Planned size | Plain-English meaning |
| --- | ---: | ---: | --- |
| Starter | ... | 30% | ... |
| Main add | ... | 40% | ... |
| Reserve | ... | 30% | ... |
```

Operation-plan example:

```bash
python scripts/portable_buy_range_plan.py TQQQ --plan
```

Typical output sections:

```text
# Technical Buy Range and Beginner Operation Plan

### Beginner Operation Plan
### Stress Scenarios
- Invalidation: ...
```

## Validation

The current version was smoke-tested with:

```bash
python scripts/portable_buy_range_plan.py --demo
python scripts/portable_buy_range_plan.py --demo --plan
python scripts/portable_buy_range_plan.py MU CLS
python scripts/portable_buy_range_plan.py TQQQ --plan
python scripts/portable_buy_range_plan.py MU --price MU=864.01
```

Invalid prices fail fast:

```bash
python scripts/portable_buy_range_plan.py MU --price MU=abc
```

## Limitations

- Public data can lag, fail, or be adjusted differently across providers.
- The tool uses daily historical prices; it is not a live trading system.
- It does not inspect fundamentals, earnings quality, news, or portfolio fit.
- Leveraged ETFs can decay quickly in volatile sideways markets.
- Buy ranges can become invalid after earnings shocks, liquidity breaks,
  major company news, or broad market regime changes.

## License

MIT
