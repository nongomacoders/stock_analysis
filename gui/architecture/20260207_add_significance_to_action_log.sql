-- Add significance column to action_log table
-- Run this migration to add the significance field for SENS analysis

-- Add the significance column
ALTER TABLE public.action_log 
ADD COLUMN IF NOT EXISTS significance varchar(20) NULL;

-- Add a comment to document the field
COMMENT ON COLUMN public.action_log.significance IS 'Significance level for SENS announcements: Low, Medium, or High';

-- Optional: Create an index if significance will be filtered frequently
-- CREATE INDEX IF NOT EXISTS idx_action_log_significance ON public.action_log(significance) WHERE significance IS NOT NULL;
