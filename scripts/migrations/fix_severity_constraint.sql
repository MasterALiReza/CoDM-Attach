-- Migration to fix data_health_checks severity constraint
-- This removes any incorrect CHECK constraint on severity column

-- Drop any existing severity check constraint (may not exist on fresh installations)
DO $$
BEGIN
    -- Try to drop the constraint if it exists
    IF EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'data_health_checks_severity_check' 
        AND conrelid = 'data_health_checks'::regclass
    ) THEN
        ALTER TABLE data_health_checks DROP CONSTRAINT data_health_checks_severity_check;
        RAISE NOTICE 'Dropped existing severity check constraint';
    END IF;
END $$;

-- Ensure severity column allows any text value
-- The application will validate severity values ('CRITICAL', 'WARNING', 'INFO')
COMMENT ON COLUMN data_health_checks.severity IS 'Severity level: CRITICAL, WARNING, or INFO (validated by application)';
