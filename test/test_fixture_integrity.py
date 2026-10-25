"""Inspect the checked-in synthetic fixture for impossible event ordering.

This test documents existing defects; it does not mutate synthetic records.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src"
ASSIGNMENT = re.compile(
    r"^\((\d+),\s*(\d+),\s*'[^']*',\s*'[^']*',\s*'[^']*',\s*'([^']+)'\)"
)
BOOKING = re.compile(
    r"^\((\d+),\s*(\d+),\s*(NULL|'[^']+'),\s*(NULL|'[^']+'),.*'(Confirmed|Cancelled|Pending)'\)"
)


def test_fixture_temporal_integrity_is_documented():
    assignments = {}
    for line in (ROOT / "assignment_history.sql").read_text().splitlines():
        match = ASSIGNMENT.match(line.strip())
        if match:
            assignments[int(match[1])] = match[3]
    invalid = []
    count = 0
    for line in (ROOT / "bookings.sql").read_text().splitlines():
        match = BOOKING.match(line.strip())
        if not match:
            continue
        count += 1
        resolved = match[3] if match[5] == "Confirmed" else match[4] if match[5] == "Cancelled" else "NULL"
        if resolved != "NULL" and resolved.strip("'") < assignments[int(match[2])]:
            invalid.append(int(match[1]))
    assert len(assignments) == 450
    assert count == 412
    # Current fixture contains known bad synthetic records; a new fixture
    # should fix them and update this explicit expected count.
    assert len(invalid) == 18
