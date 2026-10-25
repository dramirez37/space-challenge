# Astra Agent Assignment — SQL Server Decision-Support Prototype

An end-to-end **synthetic** customer-to-agent ranking demonstration using SQL Server, Python, logistic regression, and point-in-time historical features.

**Status:** research/portfolio prototype. This is not a production dispatch system, has not demonstrated real-world booking uplift, and has no externally verified predictive performance. The existing example ranking in `results/test_output.md` is a legacy artifact and **not** an out-of-sample accuracy report.

## Business question

Can historical agent outcomes help prioritize an eligible agent for an incoming customer without leaking the customer's eventual booking outcome into the recommendation?

The application calculates historical conversion/revenue metrics with a SQL Server table-valued function, trains a logistic baseline in Python using a chronological holdout, and (only with an explicit gated option) stores coefficients for a T-SQL ranking procedure.

## Repository

- `src/space_travel_agents.sql`, `src/assignment_history.sql`, `src/bookings.sql`: synthetic fixtures (30 agents, 450 assignments, 412 bookings).
- `src/create_helpers.sql`: initializes capacity and empty coefficient tables (rerunnable).
- `src/feature_pipeline.sql`: `dbo.AgentFeaturesAt` table-valued function using events strictly before an as-of timestamp.
- `src/train_weights.py`: labels, temporal integrity checks, chronological training/holdout, baseline comparisons, optional gated coefficient write.
- `src/analysis.sql`: `dbo.AssignBestAgents` stored procedure, scoring only eligible agents with saved coefficients.
- `src/generate_report.py`: illustrative reporting script; outputs are not validation.
- `test/test_temporal_pipeline.py`: tests temporal boundaries, invalid outcomes, pending cases, and evaluation contract.
- `test/test.sql`: example procedure invocation.

## Why this revision was necessary

The original project unintentionally trained on features derived from the outcome being predicted (e.g. revenue from the same eventual confirmed booking). Training normalization also differed from the SQL scoring normalization, and the availability denominator used the wrong guard.

The revised feature function uses **only histories that precede each incoming assignment**. Confirmed/cancelled outcomes contribute only after their resolution time; pending outcomes are **not automatically treated as failures**. Snapshot-only fields (such as current agent ratings) are deliberately excluded from historical training. The model uses the **same six features** in Python and SQL without incompatible transformations.

### Fixture-quality limitations

An audit found **18 synthetic booking records** where the recorded completion/cancellation precedes the associated assignment. The training routine excludes these invalid outcomes and reports their count. It does not silently correct the raw data. Historical availability is approximated from unresolved assignments; real systems should use capacity/queue events with timestamped start and release times.

These examples are fiction, not customer records. The dataset is small and may encode artificial patterns.

## Requirements

- SQL Server 2017 or newer (supports `CREATE OR ALTER`, `PERCENT_RANK` in older artifacts, `CONCAT`, and table-valued functions).
- Python 3.11+, ODBC Driver 17/18 for SQL Server, and packages in `requirements.txt`.
- Environment variable `DATABASE_URL` with a SQLAlchemy SQL Server connection URL. Do not commit credentials.

## Reproduce

1. Create an isolated SQL Server database (or use an isolated demo instance). The original fixture scripts use the current database context; review before execution.
2. Run in order with SQL Server tooling: `src/space_travel_agents.sql`, `src/assignment_history.sql`, `src/bookings.sql`, `src/create_helpers.sql`, `src/feature_pipeline.sql`, `src/analysis.sql`. Execute batches separated by `GO` correctly.
3. `python -m pip install -r requirements.txt`
4. `python -m pytest -q`
5. Set `DATABASE_URL` to the demo database. Example (no real password): `mssql+pyodbc://<user>:<password>@<host>/<database>?driver=ODBC+Driver+18+for+SQL+Server`
6. Run `python src/train_weights.py --metrics-out results/evaluation.json` **without** `--write-weights` first. Inspect temporal holdout AUC, Brier score, log loss and the constant-rate baseline. AUC alone is not adequate for probability quality.
7. To publish coefficients only if held-out Brier improves on the baseline: `python src/train_weights.py --write-weights`. This replaces seven rows in the model-weight table in one transaction. It is not a deployment to a real service.
8. Call `dbo.AssignBestAgents` as shown in `test/test.sql`, using a realistic `@AsOf` that follows the 2081 fixture history. Or run `python src/generate_report.py` to create an illustrative ranking. If validated weights have not been written, the stored procedure fails closed.

All generated metrics must be **run-derived**. Do not claim predictive performance from the sample rankings or README.

## Scoring design

Features: smoothed historical conversion rate; recent conversion; lead-source conversion; communication-channel conversion; log prior confirmed revenue; and an approximate historical availability fraction. The output is the model's logistic probability scaled to a 0–100 *MatchScore*. It is a relative decision-support score, **not** a guaranteed conversion rate.

The scoring procedure retains `@Destination`, `@Requirements`, `@LaunchLocation`, and `@CustomerName` for compatibility with the original test call, but **does not incorporate them into the learned model**. It is not a personalized destination-expertise recommendation. The reported scores are not causally identified, and historical conversion rates may reflect previous assignment policies.

## Open engineering work

- Validate on operational, time-stamped agent-capacity data, preferably with randomized or policy-aware evaluation.
- Implement explicit missing-data rules and handling of delayed labels.
- Verify SQL Server end-to-end execution in CI on a supported database instance.
- Add fairness checks, business-rule eligibility, monitoring, and full deployment controls before any production use.

## Résumé wording supported today

> Developed a synthetic agent-assignment prototype with SQL Server stored procedures, as-of SQL features, Python/logistic regression, and reproducible ranking outputs; added chronological evaluation and data-quality safeguards.

Do **not** claim proven conversion or revenue lifts without external evaluation.
