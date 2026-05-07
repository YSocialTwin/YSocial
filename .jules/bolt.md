## 2024-05-24 - Instantiating Faker Objects is CPU-intensive

**Learning:** `faker.Faker()` instantiation is extremely slow in Python. Creating a new instance on every loop iteration to generate localized mock data or populations can cause massive CPU overhead and significant performance bottlenecks.
**Action:** Always cache `faker.Faker` instances (e.g., by locale using a dictionary) when generating large numbers of mock items or agents in a loop.
