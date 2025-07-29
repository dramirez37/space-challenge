USE master;
GO
-- 1. agent_capacity: to drive availability_score
IF OBJECT_ID('dbo.agent_capacity','U') IS NULL
BEGIN
  CREATE TABLE dbo.agent_capacity (
    AgentID       INT PRIMARY KEY,
    MaxConcurrent INT        NOT NULL
  );
  -- default everyone to capacity 10
  INSERT INTO dbo.agent_capacity (AgentID, MaxConcurrent)
    SELECT AgentID, 10
      FROM dbo.space_travel_agents;
END
GO

-- 2. learned_weights_table: to hold regression weights
IF OBJECT_ID('dbo.learned_weights_table','U') IS NULL
BEGIN
  CREATE TABLE dbo.learned_weights_table (
    FeatureName VARCHAR(50) PRIMARY KEY,
    Weight      FLOAT        NOT NULL
  );
  INSERT INTO dbo.learned_weights_table (FeatureName, Weight) VALUES
    ('rating_score',            0.00),
    ('experience_score',        0.00),
    ('revenue_score',           0.00),
    ('dest_expertise_score',    0.00),
    ('lead_conversion_score',   0.00),
    ('communication_score',     0.00),
    ('requirements_score',      0.00),
    ('recency_score',           0.00),
    ('availability_score',      0.00);
END
GO
