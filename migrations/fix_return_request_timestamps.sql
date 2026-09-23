-- Run in the Supabase SQL Editor. Safe to rerun: only shift timestamps if the
-- Manila-local default has not already been installed.
DO $$
DECLARE
    existing_default text;
BEGIN
    SELECT pg_get_expr(d.adbin, d.adrelid)
    INTO existing_default
    FROM pg_attrdef AS d
    JOIN pg_attribute AS a
      ON a.attrelid = d.adrelid AND a.attnum = d.adnum
    WHERE d.adrelid = 'public.return_requests'::regclass
      AND a.attname = 'created_at';

    IF COALESCE(existing_default, '') NOT ILIKE '%Asia/Manila%' THEN
        -- Existing values were UTC wall-clock timestamps in a timestamp column.
        UPDATE public.return_requests
        SET created_at = created_at + INTERVAL '8 hours';
    END IF;
END $$;

ALTER TABLE public.return_requests
ALTER COLUMN created_at SET DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Manila');

-- Restore the student ID on existing return requests from their linked loan.
UPDATE public.return_requests AS r
SET student_id = l.student_id
FROM public.asset_loans AS l
WHERE r.loan_id = l.loan_id
  AND l.student_id IS NOT NULL
  AND l.student_id <> '';