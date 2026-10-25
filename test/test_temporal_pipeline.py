"""Offline regression checks for chronological splitting and label integrity."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from train_weights import FEATURES, classify_events, temporal_partition, evaluate


def make_fixture(n=80):
    start = pd.Timestamp("2081-01-01 00:00:00")
    times = [start + pd.Timedelta(hours=i) for i in range(n)]
    return pd.DataFrame({
        "AssignmentID": range(1, n + 1),
        "AgentID": [1 + i % 4 for i in range(n)],
        "AssignedDateTime": times,
        "LeadSource": ["Organic"] * n,
        "CommunicationMethod": ["Text"] * n,
        "BookingStatus": ["Confirmed" if i % 2 else "Cancelled" for i in range(n)],
        "BookingCompleteDate": [times[i] + pd.Timedelta(minutes=20) if i % 2 else pd.NaT for i in range(n)],
        "CancelledDate": [times[i] + pd.Timedelta(minutes=20) if not i % 2 else pd.NaT for i in range(n)],
    })


def test_leakage_boundary():
    data = make_fixture()
    d = classify_events(data)
    train, test, cutoff = temporal_partition(d)
    assert train.AssignedDateTime.max() < cutoff
    assert train.ResolvedAt.max() <= cutoff
    assert test.AssignedDateTime.min() >= cutoff
    assert len(train) > 20 and len(test) >= 10


def test_early_outcome_is_rejected():
    data = make_fixture()
    data.loc[0, "CancelledDate"] = data.loc[0, "AssignedDateTime"] - pd.Timedelta(minutes=1)
    d = classify_events(data)
    assert bool(d.loc[0, "InvalidTemporalRecord"])
    assert not bool(d.loc[0, "Usable"])


def test_pending_not_converted_to_failure():
    data = make_fixture()
    data.loc[5, "BookingStatus"] = "Pending"
    data.loc[5, "BookingCompleteDate"] = pd.NaT
    d = classify_events(data)
    assert not bool(d.loc[5, "Usable"])
    assert not bool(d.loc[5, "InvalidTemporalRecord"])


def test_training_boundary_excludes_late_resolutions():
    data = make_fixture()
    data.loc[1, "BookingCompleteDate"] = data.AssignedDateTime.max() + pd.Timedelta(days=2)
    train, _, cutoff = temporal_partition(classify_events(data))
    assert 2 not in train.AssignmentID.to_list()


def test_heldout_evaluation_returns_baseline():
    rng = np.random.default_rng(42)
    n = 120
    X = pd.DataFrame(rng.uniform(size=(n, len(FEATURES))), columns=list(FEATURES))
    X["label"] = (X["conversion_rate"] + X["recent_conversion_rate"] > 1.0).astype(int)
    model, metrics = evaluate(X.iloc[:80], X.iloc[80:])
    assert 0 <= metrics["test_auc"] <= 1
    assert metrics["test_rows"] == 40
    assert "baseline_brier" in metrics
    assert len(model.coef_[0]) == len(FEATURES)
