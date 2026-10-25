-- Compatibility shim: setup all helper tables through create_helpers.sql.
-- Setup support tables. Re-running is safe and never overwrites trained weights.
-- Execute in the intended isolated demo database (never master).
IF OBJECT_ID('dbo.agent_capacity', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.agent_capacity (
        AgentID INT NOT NULL PRIMARY KEY,
        MaxConcurrent INT NOT NULL CHECK (MaxConcurrent >= 0)
    );
    INSERT INTO dbo.agent_capacity(AgentID, MaxConcurrent)
    SELECT AgentID, 10 FROM dbo.space_travel_agents;
END;
GO
IF OBJECT_ID('dbo.learned_weights_table', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.learned_weights_table (
        FeatureName VARCHAR(64) NOT NULL PRIMARY KEY,
        Weight FLOAT NOT NULL
    );
END;
GO
