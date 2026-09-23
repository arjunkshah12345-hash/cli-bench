# Questions

Analyze `data/app.log` (one JSON object per line) and write `answers.json` in
this directory with exactly this schema:

```json
{
  "total_requests": <int>,
  "error_rate": <float, 0-1, fraction of lines with level "ERROR">,
  "top_endpoint": <string, endpoint with the most requests>,
  "p95_latency_ms": <float, 95th percentile of latency_ms (nearest-rank on sorted values)>,
  "error_counts_by_code": { "<http_status>": <int>, ... },
  "busiest_minute": <string, "YYYY-MM-DDTHH:MM" UTC minute with the most requests>,
  "slowest_request_id": <string, request_id with max latency_ms>
}
```

Rules:
- Every line with `"request"` context counts as a request; lines with context
  `"system"` or `"db"` do not.
- `error_counts_by_code` counts ERROR-level lines that have an `http_status`
  field; keys are the status as a string, include only codes that occur.
- Round `error_rate` to 4 decimal places; `p95_latency_ms` to 2 decimals.
- Sort nothing else; JSON object key order does not matter.
