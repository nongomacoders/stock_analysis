-- Create notification function for action_log changes
CREATE OR REPLACE FUNCTION notify_action_log_change()
RETURNS TRIGGER AS $$
BEGIN
    -- Send notification on action_log_changes channel
    -- Payload contains the ticker that was affected
    PERFORM pg_notify(
        'action_log_changes',
        json_build_object(
            'ticker', NEW.ticker,
            'log_id', NEW.log_id,
            'is_read', NEW.is_read
        )::text
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger on action_log table
DROP TRIGGER IF EXISTS action_log_notify_trigger ON action_log;
CREATE TRIGGER action_log_notify_trigger
    AFTER INSERT OR UPDATE ON action_log
    FOR EACH ROW
    EXECUTE FUNCTION notify_action_log_change();
