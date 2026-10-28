# Knowledge Base

Durable, curated knowledge for the project: facts agents and the owner rely on across sessions. Working notes and drafts belong in `.scratch/`; promote them here once verified.

## Sections

Create each folder when its first note is written.

| Folder | Holds |
|---|---|
| `venues/` | One note per exchange/broker: API, fees, limits, listing behaviour, data availability, known risks |
| `markets/` | Market-structure research: low-liquidity behaviour, slippage, manipulation patterns |
| `strategies/` | One note per strategy family: idea, assumptions, parameters, where it fails, linked backtests |
| `datasets/` | One **dataset card** per dataset used in backtesting (see below) |
| `backtests/` | Result summaries: strategy, dataset card, parameters, metrics, commit hash, conclusions |

## Note rules

- One topic per file, kebab-case filename, title as the first heading.
- Every factual claim about a venue or market cites its source (URL + date checked).
- Use [GLOSSARY.md](../../GLOSSARY.md) terms.

## Dataset card template

```md
# <dataset name>

- Source: <provider / venue API>
- Venue(s) & markets: <...>
- Data type & resolution: <OHLCV 1m | trades | order book L2 ...>
- Date range: <start> to <end>
- Location: <path or storage URI>
- Collected by: <script/commit>, on <date>
- Known gaps & quirks: <...>
```
