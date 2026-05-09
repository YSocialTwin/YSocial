## 2024-06-25 - Optimizing SQLAlchemy nested loops
**Learning:** In the YSocial codebase, loops over database records that make sequential database calls (N+1 query problem) are a common bottleneck.
**Action:** Always refactor these loops to use a batch fetch using SQLAlchemy's `.in_()` method, and process associations in Python memory using tools like `collections.defaultdict` to drastically reduce database roundtrips.
