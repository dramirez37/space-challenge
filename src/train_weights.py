"""Point-in-time logistic baseline for the synthetic agent-assignment challenge.

The assignment input excludes future bookings, future revenue, and current
snapshot-only fields. This demo is *not* evidence of deployed conversion gains.
Run after SQL Server setup (see README). Writes coefficients only when requested
and only when temporal holdout Brier score beats the constant-rate baseline.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

FEATURES = (
    "conversion_rate",
    "recent_conversion_rate",
    "lead_conversion_rate",
    "communication_conversion_rate",
    "log_prior_revenue",
    "availability_fraction",
)

ASSIGNMENTS_SQL = """
SELECT ah.AssignmentID, ah.AgentID, ah.AssignedDateTime,
       ah.LeadSource, ah.CommunicationMethod,
       b.BookingStatus, b.BookingCompleteDate, b.CancelledDate
FROM dbo.assignment_history ah
LEFT JOIN dbo.bookings b ON b.AssignmentID = ah.AssignmentID
ORDER BY ah.AssignedDateTime, ah.AssignmentID
"""

FEATURE_SQL = """
SELECT conversion_rate, recent_conversion_rate, lead_conversion_rate,
       communication_conversion_rate, log_prior_revenue, availability_fraction
FROM dbo.AgentFeaturesAt(:asof, :lead, :channel)
WHERE AgentID = :agent
"""


def classify_events(records: pd.DataFrame) -> pd.DataFrame:
    """Keep resolved, temporally valid outcomes; flag invalid synthetic records."""
    d = records.copy()
    for key in ("AssignedDateTime", "BookingCompleteDate", "CancelledDate"):
        d[key] = pd.to_datetime(d[key])
    status = d["BookingStatus"].fillna("Pending")
    done = np.where(status.eq("Confirmed"), d["BookingCompleteDate"],
                    d["CancelledDate"])
    d["ResolvedAt"] = pd.to_datetime(done)
    resolved = status.isin(["Confirmed", "Cancelled"])
    inconsistent = resolved & (d["ResolvedAt"].isna() |
                               (d["ResolvedAt"] < d["AssignedDateTime"]))
    d["InvalidTemporalRecord"] = inconsistent
    d["Usable"] = resolved & ~inconsistent
    d["Label"] = status.eq("Confirmed").astype(int)
    return d


def temporal_partition(records: pd.DataFrame, train_fraction: float = 0.70):
    """Split by assignment time; train labels must be resolved by cutoff."""
    if not 0 < train_fraction < 1:
        raise ValueError("train_fraction must be between 0 and 1")
    d = records.sort_values(["AssignedDateTime", "AssignmentID"])
    cutoff = d.iloc[int(len(d) * train_fraction)]["AssignedDateTime"]
    train = d[d.Usable & (d.AssignedDateTime < cutoff) & (d.ResolvedAt <= cutoff)]
    test = d[d.Usable & (d.AssignedDateTime >= cutoff)]
    if len(train) < 20 or len(test) < 10:
        raise ValueError("Not enough resolved observations for a holdout")
    return train, test, cutoff


def make_dataset(connection, observations: pd.DataFrame) -> pd.DataFrame:
    """Exact same SQL feature function used for training and serving."""
    rows = []
    for entry in observations.itertuples(index=False):
        frame = pd.read_sql_query(
            text(FEATURE_SQL), connection,
            params={"asof": entry.AssignedDateTime.to_pydatetime(),
                    "lead": entry.LeadSource,
                    "channel": entry.CommunicationMethod,
                    "agent": int(entry.AgentID)},
        )
        if len(frame) != 1:
            raise ValueError(f"Expected one feature row for assignment {entry.AssignmentID}")
        rec = frame.iloc[0].to_dict()
        rec["label"] = int(entry.Label)
        rec["assignment_id"] = int(entry.AssignmentID)
        rows.append(rec)
    return pd.DataFrame.from_records(rows)


def evaluate(train: pd.DataFrame, test: pd.DataFrame):
    if train.label.nunique() != 2 or test.label.nunique() != 2:
        raise ValueError("Both classes required for discrimination metrics")
    model = LogisticRegression(max_iter=2000, C=1.0, solver="lbfgs")
    model.fit(train[list(FEATURES)], train.label)
    prob = model.predict_proba(test[list(FEATURES)])[:, 1]
    base_rate = float(train.label.mean())
    baseline = np.full(len(test), base_rate)
    scores = {
        "train_rows": int(len(train)),
        "test_rows": int(len(test)),
        "test_auc": float(roc_auc_score(test.label, prob)),
        "test_brier": float(brier_score_loss(test.label, prob)),
        "baseline_brier": float(brier_score_loss(test.label, baseline)),
        "test_log_loss": float(log_loss(test.label, prob)),
        "baseline_log_loss": float(log_loss(test.label, baseline)),
        "train_positive_rate": base_rate,
    }
    return model, scores


def write_coefficients(connection, model):
    coeff = {"intercept": float(model.intercept_[0])}
    coeff.update(zip(FEATURES, map(float, model.coef_[0])))
    # SQL procedure requires exactly these same seven coefficients.
    connection.execute(text("DELETE FROM dbo.learned_weights_table"))
    for feature, weight in coeff.items():
        connection.execute(
            text("INSERT INTO dbo.learned_weights_table (FeatureName, Weight) "
                 "VALUES (:name, :weight)"),
            {"name": feature, "weight": weight},
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"),
                        help="SQLAlchemy URL; alternatively set DATABASE_URL")
    parser.add_argument("--metrics-out", default="results/evaluation.json")
    parser.add_argument("--write-weights", action="store_true",
                        help="Write weights only when validation beats baseline")
    args = parser.parse_args()
    if not args.database_url:
        parser.error("Provide --database-url or DATABASE_URL")
    engine = create_engine(args.database_url)
    with engine.connect() as connection:
        events = classify_events(pd.read_sql_query(text(ASSIGNMENTS_SQL), connection))
        train_events, test_events, cutoff = temporal_partition(events)
        train = make_dataset(connection, train_events)
        test = make_dataset(connection, test_events)
    model, scores = evaluate(train, test)
    scores.update({
        "cutoff": str(cutoff),
        "invalid_temporal_records": int(events.InvalidTemporalRecord.sum()),
        "unresolved_records": int((~events.Usable & ~events.InvalidTemporalRecord).sum()),
        "weights_written": False,
    })
    passes = scores["test_brier"] < scores["baseline_brier"]
    if args.write_weights and not passes:
        raise RuntimeError("Holdout Brier score did not beat baseline; weights NOT published")
    if args.write_weights:
        with engine.begin() as connection:
            write_coefficients(connection, model)
        scores["weights_written"] = True
    output = Path(args.metrics_out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(scores, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(scores, indent=2))


if __name__ == "__main__":
    main()
