## 2024-05-08 - Faker Instantiation Cost
**Learning:** Instantiating `faker.Faker` within tight loops (like population generation) is highly CPU-intensive and creates significant performance bottlenecks in this codebase.
**Action:** When generating mock data or large populations, always cache `Faker` instances (e.g., by locale using a dictionary) outside the loop to reuse them, reducing execution time substantially (up to ~10x speedup in simple tests).
