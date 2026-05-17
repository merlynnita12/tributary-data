# Tributary

Synthetic dataset for fincrime analysis practice, modeled on a fictional European payment service provider serving SMB customers.

This repo exists so the next four repos (`tributary-sql-analyses`, `tributary-dbt`, `tributary-experiments`, and `decisionlens`) have a realistic substrate to work against. Real fincrime data is locked inside companies for good reasons. The cost is that public learning material defaults to overly clean Kaggle datasets that don't capture the analytical texture of the real work. Tributary tries to close that gap.

All data is synthetic and deterministic. Run `python generate.py` and you get the same dataset every time.

## What's in it

| Table | Rows | Description |
|---|---|---|
| `customers.csv` | 50,000 | SMB customers across 12 EU countries with industry, signup date, lifecycle stage, and risk score |
| `transactions.csv` | ~5,000,000 | 18 months of card payments, SEPA transfers, refunds, and instant payments |
| `chargebacks.csv` | ~4,000 | Disputes filed against transactions, with reason codes and first-party fraud labels |
| `kyc_events.csv` | ~150,000 | Onboarding, sanctions screening, and periodic review events with risk scores at time of event |
| `compliance_alerts.csv` | ~25,000 | Transaction monitoring alerts with severity, alert type, and analyst disposition (true/false positive labels included) |
| `ground_truth_patterns.csv` | ~400 | The answer key. Lists which customers had fraud patterns embedded. Do not use during analysis. |

## Why it's shaped this way

A few design choices worth naming.

**Time window is 18 months.** Long enough to do cohort analysis, retention curves, and seasonality work. Short enough that the data loads in under 30 seconds on a laptop.

**Customer mix is SMB across the EU.** This matches the target market of the companies a senior analyst in Amsterdam fintech would likely interview at — Mollie, Wise, Adyen-style PSPs. It also gives meaningful country and industry variance for segmentation work without inflating cardinality.

**Bad actors are roughly 0.8% of customers.** Real fraud rates are noisy and vary by product, but 0.8% gives enough true positives to do anything useful while keeping the imbalanced-class problem realistic. The patterns embedded — card testing, account takeover, money muling, sanctions exposure, first-party fraud — are the five most common patterns the industry actually monitors for.

**False positive alerts outnumber true positive alerts.** This matches operational reality. The interesting question in transaction monitoring isn't "can you find fraud" but "can you find fraud without drowning analysts in cleared alerts." The synthetic alert table reflects this.

**Risk scores drift over time.** KYC events show how a customer's risk classification evolves. This supports historical analysis questions that a static snapshot wouldn't.

## What you can do with it

The dataset is designed to support, in roughly this order of difficulty:

1. SQL practice. Joins, window functions, aggregations, cohort analysis, anomaly detection. Five tables with referential relationships and enough volume to make query optimization matter.

2. dbt modeling. Staging models per source table, intermediate models for business logic (customer transaction summaries, alert triage views), mart models for specific use cases (fraud analyst queue, compliance dashboard).

3. A/B testing simulation. Pretend Tributary is testing a new fraud detection rule. Use the existing labels to simulate experiment outcomes, calculate sample sizes, run A/A tests on subsets, detect sample ratio mismatch.

4. Decision intelligence. Feed the data through a tool like DecisionLens to produce structured fincrime findings — alert volume trending, false positive analysis, sanctions screening effectiveness.

## Limitations to be honest about

- The fraud patterns are simpler than real ones. Real money muling involves complex network structures that this dataset only hints at.
- The dataset is closed-world. Real PSP analysts work with external data — sanctions lists, PEP databases, credit bureau signals, device fingerprinting. None of that is here.
- The risk score model is naive. Real risk scoring blends many signals. The score here is essentially a synthetic noise generator with realistic-looking ranges.
- The data is in EUR, PLN, SEK, and DKK only, with no FX rate handling. Multi-currency complexity is left for the analysis layer if you want it.

These limitations are deliberate. Adding more realism would make the data harder to reason about and harder to use as a teaching substrate. The point is to get the texture right without drowning in fidelity.

## Usage

If you've just cloned this repo, the easiest way to get going is to decompress the committed transactions file:

```bash
python load.py
```

This unzips `output/transactions.csv.gz` into `output/transactions.csv`. The other CSVs are committed uncompressed.

If you'd rather regenerate from scratch (same seed, same data):

```bash
python generate.py --output-dir ./output --seed 42
```

The seed defaults to 42. Change it if you want different random data; keep it the same to get reproducible results.

Output is CSVs ready to load into Snowflake, BigQuery, DuckDB, Postgres, or any other database. No external dependencies — the script uses only Python standard library.

## License

[License TBD — placeholder]

## A note on the name

Tributary, because a payment processor moves money the way tributaries feed a river — many small flows into something larger. Also it's not a real company anywhere, which means no accidental brand collision.
