-- Run once in the Supabase SQL Editor. This is separate from
-- fix_return_request_timestamps.sql; do not rerun the SQLite data migration.
BEGIN;

-- Borrow request timestamps were stored as UTC wall-clock values. Normalize
-- existing values to Philippine time and use Philippine time for new requests.
UPDATE public.borrow_requests
SET created_at = created_at + INTERVAL '8 hours';

ALTER TABLE public.borrow_requests
ALTER COLUMN created_at SET DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Manila');

-- Add the request creation time to each physical loan. Old checkout times are
-- the best available approximation for their Created At value.
ALTER TABLE public.asset_loans
ADD COLUMN IF NOT EXISTS created_at TIMESTAMP;

UPDATE public.asset_loans
SET checkout_time = checkout_time + INTERVAL '8 hours'
WHERE checkout_time IS NOT NULL;

UPDATE public.asset_loans
SET created_at = checkout_time
WHERE created_at IS NULL;

ALTER TABLE public.asset_loans
ALTER COLUMN created_at SET DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Manila');

-- New borrow approvals set checkout_time explicitly; returns set return_time
-- explicitly when approved.
ALTER TABLE public.asset_loans
ALTER COLUMN checkout_time DROP DEFAULT;

ALTER TABLE public.asset_loans
ALTER COLUMN return_time DROP DEFAULT;

COMMIT;
