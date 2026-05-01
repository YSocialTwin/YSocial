
## 2024-05-24 - N+1 Bottleneck in Population Generation
**Learning:** `generate_population` was executing 4 distinct database queries per agent, and recreating `faker.Faker` for every single agent generated inside the loop. `Faker` instantiation is very CPU-heavy, compounding the DB slowdown.
**Action:** Preload all lookup tables (`Profession`, `Education`, `Toxicity_Levels`, `Leanings`) into memory structures (`defaultdict` and normal dicts) before the generation loop, and cache `Faker` instances by `locale` in a dictionary to prevent duplicate initializations.
