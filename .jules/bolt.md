## 2024-05-24 - [Cache Faker Instances for Agent Population Generation]
**Learning:** Instantiating `faker.Faker()` is highly CPU-intensive, particularly with specific locales. Instantiating it in a loop for each agent generated in `generate_population` causes significant N-instantiations overhead and bottlenecks population creation for large demographics.
**Action:** Always maintain a dictionary cache of `faker.Faker` objects keyed by locale to reuse instances instead of re-instantiating them dynamically during mock data/population generation.
