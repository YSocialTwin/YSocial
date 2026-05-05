## 2024-05-24 - Faker Loop Cache & DB N+1 Optimization
**Learning:** Instantiating `faker.Faker` in loops is heavily CPU-intensive and can bottleneck performance severely when generating data like user populations. Additionally, looking up database values inside loops without batch fetches creates N+1 bottlenecks.
**Action:** Always pre-fetch DB lookups into dictionaries outside of loops for frequently accessed mapping tables (like traits/leanings/etc) and cache large object instances like `Faker` by locale using a dictionary outside the loop.
