## 2024-05-24 - Cache Faker Instances
**Learning:** Instantiating `faker.Faker` in a loop has massive CPU overhead.
**Action:** Cache `Faker` instances by locale when generating data in a loop.
