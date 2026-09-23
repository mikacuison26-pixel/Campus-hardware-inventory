-- Run once in the Supabase SQL Editor if asset_loans.return_time values are
-- still stored as UTC wall-clock timestamps. This changes existing values only;
-- the application already writes new return times in Philippine time.
BEGIN;

UPDATE public.asset_loans
SET return_time = return_time + INTERVAL '8 hours'
WHERE return_time IS NOT NULL;

COMMIT;
