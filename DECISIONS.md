# DECISIONS.md

1. **Indexes.**
On `employees`: unique `emp_code` guarantees business-key uniqueness; `(department, joined_on)` optimizes department filtering and headcount queries. On `attendance_logs`: unique `(emp_code, date)` prevents duplicate daily logs; `(date, emp_code)` backs paginated listing; `(emp_code, punch_in)` provides instant open-record lookups for punch-out; `(date, late_minutes, emp_code)` accelerates leaderboard aggregation.
*Rejected index:* `(department, date)` on logs—rejected because `department` lives on employees, avoiding redundant denormalization.

2. **Punch-in race.**
Both concurrent requests calculate identical `(emp_code, date)` values and issue an `insert_one`. MongoDB's unique compound index atomically accepts the first write (returning 201) and rejects the second with `DuplicateKeyError`. Our code catches this error and cleanly returns 409 Conflict.

3. **Ties.**
The pipeline uses MongoDB's `$rank` window function (competition ranking: 1, 2, 2, 4) and filters on `rank <= limit`. If two employees tie for the cutoff rank, both are returned (potentially returning more than `limit` rows), ordered by `total_late_minutes` descending and tie-broken by `emp_code` ascending.

4. **Headcount.**
The aggregation pipeline originates on `employees` (filtering `joined_on <= end_of_month`), computing `headcount = $sum: 1` before performing a `$lookup` to `attendance_logs`. Employees with zero monthly logs remain present in the grouped stream and count toward headcount without distorting attendance metrics.

5. **One thing you would change.**
At 100x scale (10M+ records), I would shard `attendance_logs` by `emp_code` and maintain incremental daily/monthly pre-aggregated rollups via MongoDB Change Streams, avoiding expensive runtime cross-collection aggregations.
