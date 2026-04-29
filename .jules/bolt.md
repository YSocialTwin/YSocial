## 2024-04-28 - N+1 Bottlenecks in Dashboard
**Learning:** The dashboard endpoints perform massive N+1 queries when loading clients and client executions for all visible experiments inside nested loops, causing severe performance degradation.
**Action:** Always batch fetch related records using `.in_()` and map them in memory using `collections.defaultdict` when aggregating nested data structures like experiments -> clients -> executions.
