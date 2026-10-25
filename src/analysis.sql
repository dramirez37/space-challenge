-- Logistic-probability scoring using coefficients fitted by train_weights.py.
-- No model has been validated or deployed merely by creating this procedure.
-- @AsOf makes historical testing reproducible; pass current time in production.
CREATE OR ALTER PROCEDURE dbo.AssignBestAgents
    @CustomerName VARCHAR(100),
    @CommunicationMethod VARCHAR(20),
    @LeadSource VARCHAR(20),
    @Destination VARCHAR(50),
    @LaunchLocation VARCHAR(100),
    @Requirements VARCHAR(200),
    @AsOf DATETIME2(0) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SET @AsOf = COALESCE(@AsOf, SYSUTCDATETIME());

    IF (SELECT COUNT(*) FROM dbo.learned_weights_table
        WHERE FeatureName IN ('intercept', 'conversion_rate', 'recent_conversion_rate',
          'lead_conversion_rate', 'communication_conversion_rate', 'log_prior_revenue',
          'availability_fraction')) <> 7
        THROW 50001, 'Validated model coefficients are missing; train and evaluate first.', 1;

    ;WITH w AS (
        SELECT
          MAX(CASE WHEN FeatureName='intercept' THEN Weight END) AS intercept,
          MAX(CASE WHEN FeatureName='conversion_rate' THEN Weight END) AS conversion_weight,
          MAX(CASE WHEN FeatureName='recent_conversion_rate' THEN Weight END) AS recent_weight,
          MAX(CASE WHEN FeatureName='lead_conversion_rate' THEN Weight END) AS lead_weight,
          MAX(CASE WHEN FeatureName='communication_conversion_rate' THEN Weight END) AS channel_weight,
          MAX(CASE WHEN FeatureName='log_prior_revenue' THEN Weight END) AS revenue_weight,
          MAX(CASE WHEN FeatureName='availability_fraction' THEN Weight END) AS availability_weight
        FROM dbo.learned_weights_table
    ),
    linear_scores AS (
        SELECT
          f.AgentID, f.AgentName, f.available_slots,
          w.intercept +
          w.conversion_weight * f.conversion_rate +
          w.recent_weight * f.recent_conversion_rate +
          w.lead_weight * f.lead_conversion_rate +
          w.channel_weight * f.communication_conversion_rate +
          w.revenue_weight * f.log_prior_revenue +
          w.availability_weight * f.availability_fraction AS logit
        FROM dbo.AgentFeaturesAt(@AsOf, @LeadSource, @CommunicationMethod) AS f
        CROSS JOIN w
        WHERE f.available_slots > 0
    )
    SELECT AgentID, AgentName, available_slots AS AvailableSlots,
           CAST(100.0 / (1.0 + EXP(-CASE
             WHEN logit > 35.0 THEN 35.0
             WHEN logit < -35.0 THEN -35.0
             ELSE logit END)) AS DECIMAL(5,1)) AS MatchScore
    FROM linear_scores
    ORDER BY MatchScore DESC, AgentID;
END;
GO
