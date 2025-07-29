USE master;
GO

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
