-- Run in the Supabase SQL Editor to repair existing return requests whose
-- student_id is blank or the literal placeholder "EMPTY".
BEGIN;

UPDATE public.return_requests AS r
SET student_id = l.student_id
FROM public.asset_loans AS l
WHERE r.loan_id = l.loan_id
  AND UPPER(BTRIM(COALESCE(r.student_id, ''))) IN ('', 'EMPTY')
  AND NULLIF(BTRIM(COALESCE(l.student_id, '')), '') IS NOT NULL
  AND UPPER(BTRIM(l.student_id)) <> 'EMPTY';

COMMIT;

-- Any rows still returned here need a valid student_id on their linked loan
-- before they can be repaired automatically.
SELECT r.request_id, r.loan_id, r.student_id, l.student_id AS loan_student_id
FROM public.return_requests AS r
LEFT JOIN public.asset_loans AS l ON l.loan_id = r.loan_id
WHERE UPPER(BTRIM(COALESCE(r.student_id, ''))) IN ('', 'EMPTY');
