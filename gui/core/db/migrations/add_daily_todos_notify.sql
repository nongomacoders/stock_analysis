-- Function to send a notification when daily_todos changes
CREATE OR REPLACE FUNCTION notify_daily_todos_change()
RETURNS TRIGGER AS $$
BEGIN
    -- The payload can be anything. The client will just be triggered to refresh.
    -- We use the channel 'daily_todos_changes'.
    PERFORM pg_notify('daily_todos_changes', 'update');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Drop the trigger if it already exists to ensure a clean setup
DROP TRIGGER IF EXISTS daily_todos_notify_trigger ON daily_todos;

-- Create the trigger to execute the function after any INSERT, UPDATE, or DELETE
CREATE TRIGGER daily_todos_notify_trigger
AFTER INSERT OR UPDATE OR DELETE ON daily_todos
FOR EACH ROW EXECUTE FUNCTION notify_daily_todos_change();