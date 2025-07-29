-- =======================================================================
-- Author:   David Ramirez
-- Purpose:  Rank Space Travel Agents for a new customer
--           with percentile‐rank normalization + recency & availability
-- =======================================================================
CREATE OR ALTER PROCEDURE dbo.AssignBestAgents
  @CustomerName        VARCHAR(100),
  @CommunicationMethod VARCHAR(20),
  @LeadSource          VARCHAR(20),
  @Destination         VARCHAR(50),
  @LaunchLocation      VARCHAR(100),
  @Requirements        VARCHAR(200)
AS
BEGIN
  SET NOCOUNT ON;

  ;WITH
  -- 0) Start date for recency calculation: 30 days before the latest booking
  recency_start_date AS (
    SELECT DATEADD(DAY, -30, MAX(BookingCompleteDate)) AS start_date
    FROM dbo.bookings
  ),

  -- 1) Aggregate each agent’s history
  agent_bookings AS (
    SELECT
      a.AgentID,
      a.FirstName + ' ' + a.LastName             AS AgentName,
      a.DepartmentName,
      a.AverageCustomerServiceRating,
      a.YearsOfService,
      COUNT(DISTINCT ah.AssignmentID)             AS total_assignments,
      SUM(CASE WHEN b.BookingStatus='Confirmed' THEN 1 ELSE 0 END) AS confirmed_bookings,
      SUM(CASE WHEN b.BookingStatus='Confirmed' THEN b.TotalRevenue ELSE 0 END) AS total_revenue,
      SUM(CASE WHEN b.BookingStatus='Confirmed' AND b.Destination = @Destination THEN 1 ELSE 0 END) AS dest_confirmed_bookings,
      SUM(CASE WHEN ah.LeadSource = @LeadSource AND b.BookingStatus='Confirmed' THEN 1 ELSE 0 END) AS lead_source_converted,
      SUM(CASE WHEN ah.LeadSource = @LeadSource THEN 1 ELSE 0 END) AS lead_source_assignments,
      SUM(CASE WHEN ah.CommunicationMethod = @CommunicationMethod AND b.BookingStatus='Confirmed' THEN 1 ELSE 0 END) AS comm_converted,
      SUM(CASE WHEN ah.CommunicationMethod = @CommunicationMethod THEN 1 ELSE 0 END) AS comm_assignments
    FROM dbo.space_travel_agents    AS a
    LEFT JOIN dbo.assignment_history AS ah ON a.AgentID = ah.AgentID
    LEFT JOIN dbo.bookings           AS b  ON ah.AssignmentID = b.AssignmentID
    GROUP BY
      a.AgentID, a.FirstName, a.LastName,
      a.DepartmentName,
      a.AverageCustomerServiceRating,
      a.YearsOfService
  ),

  -- 2) Recency: fraction of confirmed bookings in past 30 days
  recency AS (
    SELECT
      ah.AgentID,
      SUM(CASE WHEN b.BookingStatus='Confirmed'
               AND b.BookingCompleteDate >= rsd.start_date
               THEN 1 ELSE 0 END) * 1.0
        / NULLIF(SUM(CASE WHEN b.BookingStatus='Confirmed' THEN 1 END),0)
      AS raw_recency
    FROM dbo.assignment_history AS ah
    LEFT JOIN dbo.bookings b ON ah.AssignmentID = b.AssignmentID
    CROSS JOIN recency_start_date rsd
    GROUP BY ah.AgentID
  ),

  -- 3) Availability: 1 – (pending assignments / capacity)
  availability AS (
    SELECT
      ah.AgentID,
      1.0
      - SUM(CASE WHEN b.BookingStatus='Pending' THEN 1 ELSE 0 END)*1.0
        / NULLIF(cap.MaxConcurrent,1)
      AS raw_availability
    FROM dbo.assignment_history AS ah
    LEFT JOIN dbo.bookings           AS b   ON ah.AssignmentID = b.AssignmentID
    JOIN dbo.agent_capacity          AS cap ON ah.AgentID      = cap.AgentID
    GROUP BY ah.AgentID, cap.MaxConcurrent
  ),

  -- 4) Base metrics + requirement flag
  base AS (
    SELECT
      ab.*,
      CASE WHEN ab.confirmed_bookings>0
           THEN ab.dest_confirmed_bookings*1.0/ab.confirmed_bookings
           ELSE 0 END                                   AS dest_expertise_score,
      CASE WHEN ab.lead_source_assignments>0
           THEN ab.lead_source_converted*1.0/ab.lead_source_assignments
           ELSE 0 END                                   AS lead_conversion_score,
      CASE WHEN ab.comm_assignments>0
           THEN ab.comm_converted*1.0/ab.comm_assignments
           ELSE 0 END                                   AS communication_score,
      CASE WHEN ab.DepartmentName='Luxury Voyages'
            AND @Requirements LIKE '%Luxury%' THEN 1 ELSE 0 END   AS requirements_score,
      ISNULL(r.raw_recency,0)        AS recency_score,
      ISNULL(a.raw_availability,1)   AS availability_score
    FROM agent_bookings    AS ab
    LEFT JOIN recency      AS r  ON ab.AgentID = r.AgentID
    LEFT JOIN availability AS a  ON ab.AgentID = a.AgentID
  ),

  -- 5) Percentile‐rank normalization over all agents
  pct AS (
    SELECT
      b.AgentID,
      b.AgentName,
      PERCENT_RANK() OVER (ORDER BY b.AverageCustomerServiceRating)  AS rating_pct,
      PERCENT_RANK() OVER (ORDER BY b.YearsOfService)               AS experience_pct,
      PERCENT_RANK() OVER (ORDER BY b.total_revenue)               AS revenue_pct,
      PERCENT_RANK() OVER (ORDER BY b.dest_expertise_score)        AS dest_expertise_pct,
      PERCENT_RANK() OVER (ORDER BY b.lead_conversion_score)       AS lead_conversion_pct,
      PERCENT_RANK() OVER (ORDER BY b.communication_score)         AS communication_pct,
      b.requirements_score                                         AS requirements_score,
      PERCENT_RANK() OVER (ORDER BY b.recency_score)               AS recency_pct,
      PERCENT_RANK() OVER (ORDER BY b.availability_score)          AS availability_pct
    FROM base AS b
  ),

  -- 6) Regression‐learned weights
  weights AS (
    SELECT
      MAX(CASE WHEN FeatureName='rating_score'          THEN Weight END) AS w_rating,
      MAX(CASE WHEN FeatureName='experience_score'      THEN Weight END) AS w_experience,
      MAX(CASE WHEN FeatureName='revenue_score'         THEN Weight END) AS w_revenue,
      MAX(CASE WHEN FeatureName='dest_expertise_score'  THEN Weight END) AS w_dest_expertise,
      MAX(CASE WHEN FeatureName='lead_conversion_score' THEN Weight END) AS w_lead_conversion,
      MAX(CASE WHEN FeatureName='communication_score'   THEN Weight END) AS w_communication,
      MAX(CASE WHEN FeatureName='requirements_score'    THEN Weight END) AS w_requirements,
      MAX(CASE WHEN FeatureName='recency_score'         THEN Weight END) AS w_recency,
      MAX(CASE WHEN FeatureName='availability_score'    THEN Weight END) AS w_availability
    FROM dbo.learned_weights_table
  ),

  -- 7) Calculate Raw Score
  raw_scores AS (
    SELECT
      p.AgentID,
      p.AgentName,
      (
        p.rating_pct         * w.w_rating
      + p.experience_pct     * w.w_experience
      + p.revenue_pct        * w.w_revenue
      + p.dest_expertise_pct * w.w_dest_expertise
      + p.lead_conversion_pct* w.w_lead_conversion
      + p.communication_pct  * w.w_communication
      + p.requirements_score * w.w_requirements
      + p.recency_pct        * w.w_recency
      + p.availability_pct   * w.w_availability
      ) AS final_score
    FROM pct AS p
    CROSS JOIN weights AS w
  )
  -- 8) Final Ranked & Scaled List
  SELECT
    rs.AgentID,
    rs.AgentName,
    CAST(
        (rs.final_score - min_s.min_score) * 100.0 / (max_s.max_score - min_s.min_score)
        AS DECIMAL(5, 1)
    ) AS MatchScore
  FROM raw_scores AS rs
  CROSS JOIN (SELECT MIN(final_score) AS min_score FROM raw_scores) AS min_s
  CROSS JOIN (SELECT MAX(final_score) AS max_score FROM raw_scores) AS max_s
  ORDER BY MatchScore DESC;
END;
GO
