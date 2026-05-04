## 2024-05-04 - Cache Faker objects during loops
**Learning:** In the YSocial architecture, simulating populations generates thousands of fake identities. `faker.Faker(locale)` instantiation is extremely slow. When bulk-generating data via agents, creating a new `Faker` object per row creates a severe CPU bottleneck.
**Action:** Always maintain a locale-based cache for `Faker` instances in data generation loops, rather than repeatedly instantiating them on each iteration.
