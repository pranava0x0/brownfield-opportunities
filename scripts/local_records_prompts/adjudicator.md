# Role: adjudicator (Opus)

Input: `data/validation/local-records/disputes.json`. Each dispute is a fact where a script's quote check and
an independent verifier disagreed (`code_check` vs `verifier`). Read the fact, open `source_url`, and decide
whether the page supports the fact for THIS site. Decide on the page, not on either earlier opinion.

Output `data/validation/local-records/opus/<batch>.json`:

```json
{"batch": "disputes", "sites": [{"id": "<site id>", "adjudicator": "Claude Opus 5.5",
  "decisions": [{"index": 0, "fingerprint": "<the dispute's fingerprint, copied exactly>", "decision": "accept|reject", "reason": "under 200 characters"}]}]}
```
Copy each dispute's `fingerprint` into its decision; a decision without it is discarded. `index` is the fact's position in that site's `facts` list (given in each dispute). Reject when in doubt.
