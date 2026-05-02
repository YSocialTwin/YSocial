## 2024-05-24 - Caching Faker instances by locale in data generation loops
**Learning:** Instantiating `faker.Faker` objects is heavily CPU-intensive. Creating a new instance on every iteration of a loop (e.g. when generating large populations of agents) causes a massive performance bottleneck.
**Action:** When generating mock data or populations in loops, cache `Faker` instances by locale in a dictionary outside the loop rather than creating new instances on every iteration.
