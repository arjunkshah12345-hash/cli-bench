# CSV Normalization Spec

Input: `input.csv` with header `id,Name,Email,SignupDate,Plan,MRR_USD` (order fixed).
Output: `output.csv` with header exactly:

```
id,name,email,signup_date,plan,mrr_usd
```

## Field rules

**name** — trim whitespace, then Title Case each word (e.g. `  aLICE  SMITH ` → `Alice Smith`).
Empty after trimming → `unknown`.

**email** — trim, lowercase. Valid only if it contains exactly one `@`, the domain
part contains a dot, and it contains no spaces. Invalid or empty → empty string.

**signup_date** — input may be in any of these formats:
1. `YYYY-MM-DD`
2. `MM/DD/YYYY`
3. `Month DD, YYYY` (e.g. `March 1, 2024`)
4. `YYYY-MM-DD HH:MM:SS`

Normalize to `YYYY-MM-DD` (drop the time part for format 4). Unparseable → empty string.

**plan** — trim, lowercase. Valid values: `basic`, `pro`, `enterprise`.
Anything else → `unknown`.

**mrr_usd** — may be: a plain number (`49`), with dollars (`$49.00`), with
thousands separators (`1,200.00`), the word `free` (case-insensitive), or empty.
`free` and empty → `0.00`. Strip `$` and commas, parse as float; negative → `0.00`.
Format with exactly two decimals.

## Row rules

- Preserve the `id` column as-is.
- Sort rows by: `plan` ascending (alphabetical, `unknown` sorts like any string),
  then `mrr_usd` descending (numeric), then `email` ascending (empty first),
  then `id` ascending (numeric).
- Do not quote any values; no value will contain a comma after normalization.
