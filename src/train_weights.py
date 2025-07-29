# =========================================================================
# Author:   David Ramirez
# Purpose:  Train weights for the agent assignment model
# =========================================================================
import os
import pandas as pd
from sqlalchemy import create_engine, text
from sklearn.linear_model import LogisticRegression

def main():
    db_password = os.environ.get('PASSWORD')
    if not db_password:
        raise ValueError("Database password not found in environment variable 'PASSWORD'")

    # 1) Connect via SQLAlchemy
    connection_string = (
        f"mssql+pyodbc://SA:{db_password}@localhost,1435/master"
        f"?driver=ODBC+Driver+17+for+SQL+Server"
    )
    engine = create_engine(connection_string)
    print("Connecting to master…")


    # 2) Load historical dataset with canonical feature names
    sql = """
    WITH
      -- 0) Start date for recency calculation: 30 days before the latest booking
      recency_start_date AS (
        SELECT DATEADD(DAY, -30, MAX(BookingCompleteDate)) AS start_date
        FROM dbo.bookings
      ),
      -- revenue per assignment
      b_rev AS (
        SELECT AssignmentID,
               SUM(TotalRevenue) AS total_revenue
        FROM bookings
        WHERE BookingStatus='Confirmed'
        GROUP BY AssignmentID
      ),
      -- total confirms per agent
      conf AS (
        SELECT ah.AgentID,
               COUNT(*) AS total_confirms
        FROM assignment_history ah
        JOIN bookings b ON ah.AssignmentID=b.AssignmentID
        WHERE b.BookingStatus='Confirmed'
        GROUP BY ah.AgentID
      ),
      -- destination expertise per agent
      dest AS (
        SELECT ah.AgentID,
               COUNT(*) AS dest_confirms
        FROM assignment_history ah
        JOIN bookings b ON ah.AssignmentID=b.AssignmentID
        WHERE b.BookingStatus='Confirmed'
          AND b.Destination='Mars' -- NOTE: This is hardcoded for training
        GROUP BY ah.AgentID
      ),
      -- leads assigned per agent
      leads AS (
        SELECT AgentID,
               COUNT(*) AS total_leads
        FROM assignment_history
        WHERE LeadSource='Organic' -- NOTE: This is hardcoded for training
        GROUP BY AgentID
      ),
      -- leads converted per agent
      lead_conv AS (
        SELECT ah.AgentID,
               COUNT(*) AS lead_converts
        FROM assignment_history ah
        JOIN bookings b ON ah.AssignmentID=b.AssignmentID
        WHERE ah.LeadSource='Organic' -- NOTE: This is hardcoded for training
          AND b.BookingStatus='Confirmed'
        GROUP BY ah.AgentID
      ),
      -- comms assigned per agent
      comms AS (
        SELECT AgentID,
               COUNT(*) AS total_comm
        FROM assignment_history
        WHERE CommunicationMethod='Phone Call' -- NOTE: This is hardcoded for training
        GROUP BY AgentID
      ),
      -- comms converted per agent
      comm_conv AS (
        SELECT ah.AgentID,
               COUNT(*) AS comm_converts
        FROM assignment_history ah
        JOIN bookings b ON ah.AssignmentID=b.AssignmentID
        WHERE ah.CommunicationMethod='Phone Call' -- NOTE: This is hardcoded for training
          AND b.BookingStatus='Confirmed'
        GROUP BY ah.AgentID
      ),
      rec AS (
        SELECT ah.AgentID,
               SUM(CASE
                     WHEN b.BookingStatus='Confirmed'
                       AND b.BookingCompleteDate >= rsd.start_date
                     THEN 1 ELSE 0 END)*1.0
                 / NULLIF(SUM(CASE WHEN b.BookingStatus='Confirmed' THEN 1 END),0)
               AS recency_score
        FROM assignment_history ah
        LEFT JOIN bookings b ON ah.AssignmentID=b.AssignmentID
        CROSS JOIN recency_start_date rsd
        GROUP BY ah.AgentID
      ),
      -- availability: 1 – pending/capacity
      avail AS (
        SELECT ah.AgentID,
               1.0
               - SUM(CASE WHEN b.BookingStatus='Pending' THEN 1 ELSE 0 END)*1.0
                 / NULLIF(cap.MaxConcurrent,1)
               AS availability_score
        FROM assignment_history ah
        LEFT JOIN bookings b ON ah.AssignmentID=b.AssignmentID
        JOIN agent_capacity cap ON ah.AgentID=cap.AgentID
        GROUP BY ah.AgentID, cap.MaxConcurrent
      )
    SELECT
      ah.AssignmentID,
      ah.AgentID,
      a.AverageCustomerServiceRating AS rating_score,
      a.YearsOfService             AS experience_score,
      COALESCE(b_rev.total_revenue,0) AS revenue_score,
      CASE WHEN conf.total_confirms>0
           THEN dest.dest_confirms*1.0/conf.total_confirms ELSE 0 END
        AS dest_expertise_score,
      CASE WHEN leads.total_leads>0
           THEN lead_conv.lead_converts*1.0/leads.total_leads ELSE 0 END
        AS lead_conversion_score,
      CASE WHEN comms.total_comm>0
           THEN comm_conv.comm_converts*1.0/comms.total_comm ELSE 0 END
        AS communication_score,
      CASE WHEN a.DepartmentName='Luxury Voyages'
            AND ah.LeadSource LIKE '%Organic%' THEN 1 ELSE 0 END
        AS requirements_score,
      ISNULL(rec.recency_score,0)        AS recency_score,
      ISNULL(avail.availability_score,1) AS availability_score,
      CASE WHEN b.BookingStatus='Confirmed' THEN 1 ELSE 0 END AS outcome
    FROM assignment_history ah
    JOIN space_travel_agents a ON ah.AgentID=a.AgentID
    LEFT JOIN bookings b ON ah.AssignmentID=b.AssignmentID
    LEFT JOIN b_rev    ON ah.AssignmentID=b_rev.AssignmentID
    LEFT JOIN conf    ON ah.AgentID=conf.AgentID
    LEFT JOIN dest    ON ah.AgentID=dest.AgentID
    LEFT JOIN leads   ON ah.AgentID=leads.AgentID
    LEFT JOIN lead_conv ON ah.AgentID=lead_conv.AgentID
    LEFT JOIN comms   ON ah.AgentID=comms.AgentID
    LEFT JOIN comm_conv ON ah.AgentID=comm_conv.AgentID
    LEFT JOIN rec    ON ah.AgentID=rec.AgentID
    LEFT JOIN avail  ON ah.AgentID=avail.AgentID
    ;
    """

    df = pd.read_sql(sql, engine)
    print("Fetched training data:", df.shape, "rows")

    # 3) Define feature columns
    feature_cols = [
        'rating_score',
        'experience_score',
        'revenue_score',
        'dest_expertise_score',
        'lead_conversion_score',
        'communication_score',
        'requirements_score',
        'recency_score',
        'availability_score'
    ]
    print("Features:", feature_cols)
    
    # Normalize features to match the PERCENT_RANK logic in SQL
    print("Normalizing features to percentile ranks...")
    for col in feature_cols:
        df[col] = df[col].rank(pct=True)

    X = df[feature_cols]
    y = df['outcome']

    # 4) Train
    model = LogisticRegression(fit_intercept=False, solver='liblinear')
    model.fit(X, y)
    learned = dict(zip(feature_cols, model.coef_[0]))
    print("Learned weights:")
    for k,v in learned.items():
        print(f"  {k}: {v:.6f}")

    # 5) Persist back to SQL
    with engine.begin() as conn:
        for feat, w in learned.items():
            conn.execute(
                text("UPDATE dbo.learned_weights_table SET Weight=:w WHERE FeatureName=:f"),
                {"w": float(w), "f": feat}
            )
    print("Updated learned_weights_table successfully.")

if __name__ == "__main__":
    main()
