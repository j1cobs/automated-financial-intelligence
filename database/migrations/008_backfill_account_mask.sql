-- Rows inserted before `mask` was populated have it NULL, which defeats the mask veto in
-- canonicalize_account_keys: NULL never disqualifies a candidate, so two maskless legacy rows
-- both stay in the running and the len(matches)==1 guard bails, permanently blocking the merge.
-- account_name already embeds the mask (plaid_ingestor.py:58 formats "<name> (••••<mask>)"),
-- so recover it from there. Idempotent and end-anchored, so names containing their own
-- parentheses (e.g. "... (FHSA) CAD (••••JJWQ)") resolve to the trailing group.
UPDATE accounts
SET mask = substring(account_name from '\(•+([^)]+)\)$')
WHERE mask IS NULL
  AND account_name ~ '\(•+([^)]+)\)$';
