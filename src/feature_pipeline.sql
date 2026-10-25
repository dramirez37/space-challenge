-- Reusable point-in-time features for training and scoring.
-- Every event is evaluated using information available strictly before @AsOf.
-- Agent rating/tenure are deliberately excluded: the fixtures contain only their
-- current snapshots, not the historical values needed for leakage-free training.
CREATE OR ALTER FUNCTION dbo.AgentFeaturesAt (
    @AsOf DATETIME2(0),
    @LeadSource VARCHAR(20),
    @CommunicationMethod VARCHAR(20)
)
RETURNS TABLE
AS
RETURN
(
    WITH historical_events AS (
        SELECT
            ah.AgentID,
            ah.AssignedDateTime,
            ah.LeadSource,
            ah.CommunicationMethod,
            CASE WHEN b.BookingStatus = 'Confirmed'
                      AND b.BookingCompleteDate >= ah.AssignedDateTime
                      AND b.BookingCompleteDate < @AsOf
                 THEN 1 ELSE 0 END AS is_confirmed,
            CASE WHEN b.BookingStatus = 'Cancelled'
                      AND b.CancelledDate >= ah.AssignedDateTime
                      AND b.CancelledDate < @AsOf
                 THEN 1 ELSE 0 END AS is_cancelled,
            CASE WHEN b.BookingStatus = 'Confirmed'
                      AND b.BookingCompleteDate >= ah.AssignedDateTime
                      AND b.BookingCompleteDate < @AsOf
                 THEN COALESCE(b.TotalRevenue, 0.0) ELSE 0.0 END AS confirmed_revenue
        FROM dbo.assignment_history AS ah
        LEFT JOIN dbo.bookings AS b ON b.AssignmentID = ah.AssignmentID
        WHERE ah.AssignedDateTime < @AsOf
    ),
    history_summary AS (
        SELECT
            AgentID,
            SUM(is_confirmed) AS confirmed_count,
            SUM(is_cancelled) AS cancelled_count,
            SUM(confirmed_revenue) AS confirmed_revenue,
            SUM(CASE WHEN AssignedDateTime >= DATEADD(DAY, -30, @AsOf)
                     THEN is_confirmed ELSE 0 END) AS recent_confirmed,
            SUM(CASE WHEN AssignedDateTime >= DATEADD(DAY, -30, @AsOf)
                     THEN is_cancelled ELSE 0 END) AS recent_cancelled,
            SUM(CASE WHEN LeadSource = @LeadSource
                     THEN is_confirmed ELSE 0 END) AS lead_confirmed,
            SUM(CASE WHEN LeadSource = @LeadSource
                     THEN is_cancelled ELSE 0 END) AS lead_cancelled,
            SUM(CASE WHEN CommunicationMethod = @CommunicationMethod
                     THEN is_confirmed ELSE 0 END) AS channel_confirmed,
            SUM(CASE WHEN CommunicationMethod = @CommunicationMethod
                     THEN is_cancelled ELSE 0 END) AS channel_cancelled,
            SUM(CASE WHEN is_confirmed = 0 AND is_cancelled = 0
                     THEN 1 ELSE 0 END) AS unresolved_assignments
        FROM historical_events
        GROUP BY AgentID
    )
    SELECT
        a.AgentID,
        CONCAT(a.FirstName, ' ', a.LastName) AS AgentName,
        a.DepartmentName,
        CAST((1.0 + COALESCE(s.confirmed_count, 0)) /
             (2.0 + COALESCE(s.confirmed_count, 0) + COALESCE(s.cancelled_count, 0))
             AS FLOAT) AS conversion_rate,
        CAST((1.0 + COALESCE(s.recent_confirmed, 0)) /
             (2.0 + COALESCE(s.recent_confirmed, 0) + COALESCE(s.recent_cancelled, 0))
             AS FLOAT) AS recent_conversion_rate,
        CAST((1.0 + COALESCE(s.lead_confirmed, 0)) /
             (2.0 + COALESCE(s.lead_confirmed, 0) + COALESCE(s.lead_cancelled, 0))
             AS FLOAT) AS lead_conversion_rate,
        CAST((1.0 + COALESCE(s.channel_confirmed, 0)) /
             (2.0 + COALESCE(s.channel_confirmed, 0) + COALESCE(s.channel_cancelled, 0))
             AS FLOAT) AS communication_conversion_rate,
        CAST(LOG(1.0 + COALESCE(s.confirmed_revenue, 0.0)) AS FLOAT) AS log_prior_revenue,
        CAST(
            CASE WHEN cap.MaxConcurrent <= 0 THEN 0.0
                 WHEN COALESCE(s.unresolved_assignments, 0) >= cap.MaxConcurrent THEN 0.0
                 ELSE (cap.MaxConcurrent - COALESCE(s.unresolved_assignments, 0)) * 1.0 /
                      NULLIF(cap.MaxConcurrent, 0)
            END AS FLOAT
        ) AS availability_fraction,
        CASE WHEN cap.MaxConcurrent <= 0 THEN 0
             WHEN COALESCE(s.unresolved_assignments, 0) >= cap.MaxConcurrent THEN 0
             ELSE cap.MaxConcurrent - COALESCE(s.unresolved_assignments, 0)
        END AS available_slots
    FROM dbo.space_travel_agents AS a
    INNER JOIN dbo.agent_capacity AS cap ON cap.AgentID = a.AgentID
    LEFT JOIN history_summary AS s ON s.AgentID = a.AgentID
);
GO
