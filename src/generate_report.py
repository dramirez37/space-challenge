"""Produce a reproducible demo ranking after validated coefficients are written.

This is a synthetic illustration, not a performance evaluation. For evaluation
results, run train_weights.py and inspect its holdout metrics file.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    parser.add_argument("--as-of", default="2081-04-11T00:00:00")
    parser.add_argument("--out", default="results/current_demo_ranking.md")
    args = parser.parse_args()
    if not args.database_url:
        parser.error("Set DATABASE_URL or pass --database-url")
    engine = create_engine(args.database_url)
    query = text("""
    EXEC dbo.AssignBestAgents
        @CustomerName = :name,
        @CommunicationMethod = :channel,
        @LeadSource = :lead,
        @Destination = :dest,
        @LaunchLocation = :launch,
        @Requirements = :requirements,
        @AsOf = :asof
    """)
    with engine.connect() as connection:
        agents = pd.read_sql_query(
            query, connection,
            params={"name": "Synthetic Customer", "channel": "Phone Call",
                    "lead": "Organic", "dest": "Mars",
                    "launch": "Earth Orbital Station",
                    "requirements": "Luxury Dome Stay", "asof": args.as_of},
        )
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "# Synthetic agent ranking (illustrative only)\n\n"
        "Not an out-of-sample validation report or evidence of uplift.\n\n"
        + agents.to_markdown(index=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(agents)} ranked agents to {output}")


if __name__ == "__main__":
    main()
