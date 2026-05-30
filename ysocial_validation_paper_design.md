# Design for a Validation Paper on YSocial Simulations

## Objective

Design a paper whose central claim is:

> **YSocial reliably simulates online social environments, and the generated scenarios are stable once the initial settings are defined.**

This claim should be framed carefully. The platform can likely support a strong **empirical reliability and controlled-sensitivity** claim, but not an unrestricted claim of deterministic reproducibility across all LLM backends, temperatures, scales, and runtime modes. The paper should therefore validate:

- **stability**: repeated runs under the same settings yield statistically similar macro outcomes
- **sensitivity**: key parameters and recommender choices induce systematic, interpretable changes
- **robustness**: results remain consistent across implementation choices that should not materially alter behavior
- **traceability**: the platform logs enough configuration and runtime state to support post hoc auditing
- **bounded guarantees**: YSocial guarantees configuration-level control and observable regime stability, not exact pathwise identity of every run

---

## 1. Paper Positioning

### Core contribution

This is a **simulation validation and methodology paper**. It is not mainly about a substantive social-science finding. Its contribution is to establish what kind of scientific evidence YSocial can support.

### Main research questions

**RQ1. Stability**

When the same scenario is repeated under fixed initial settings, how much variance appears in:

- final topology
- user behavior
- content production
- content visibility
- opinion evolution

**RQ2. Sensitivity**

Which parameters are the main drivers of:

- network structure
- engagement patterns
- visibility inequality
- polarization and topic concentration

**RQ3. Recommender effects**

How strongly do content and follow recommenders shape the final system state relative to other parameters such as initial topology, activity, or opinion settings?

**RQ4. Runtime robustness**

Do backend/runtime substitutions that should be implementation details, such as database backend or Redis acceleration, preserve the same macro behavior?

**RQ5. Guarantees**

What guarantees can YSocial honestly provide regarding repeatability, observability, robustness, and valid operating envelopes?

---

## 2. Validation Philosophy

The paper should validate YSocial at **three levels**.

### Level A. Software and execution validity

Does the platform execute the intended experiment faithfully?

Targets:

- config parsing correctness
- experiment/client/server contract consistency
- runtime completion under expected conditions
- logging completeness
- database consistency
- plugin/runtime availability checks

### Level B. Statistical stability

Do repeated runs under identical settings remain in the same outcome regime?

Targets:

- low dispersion for macro metrics
- preserved rank ordering between experimental conditions
- confidence intervals narrow enough for comparative research

### Level C. Mechanistic sensitivity

Do parameter changes produce interpretable directional changes?

Targets:

- recommenders alter visibility and network growth in expected ways
- opinion parameters alter convergence or polarization in expected ways
- activity and churn alter volume and topology turnover
- memory alters continuity and path dependence

---

## 3. What Should Count as a Guarantee

The paper should avoid overclaiming exact reproducibility. The right guarantee language is:

### Guarantee G1. Configuration traceability

Given a completed run, YSocial preserves the scenario definition through:

- experiment JSON
- client JSON
- population files
- runtime DB contents
- structured logs

### Guarantee G2. Operational repeatability

Given fixed scenario settings and supported runtime conditions, YSocial can rerun the same scenario family with stable macro-level outputs.

### Guarantee G3. Controlled sensitivity

Changing major parameters, especially recommenders, activity schedules, and opinion-dynamics parameters, changes outcomes in systematic rather than arbitrary ways.

### Guarantee G4. Backend robustness within envelope

Storage and orchestration choices that are intended as infrastructure substitutions, such as SQLite versus PostgreSQL or Redis on/off, should preserve macro outcomes up to bounded variance.

### Guarantee G5. Auditability

The platform exposes enough intermediate and final state to diagnose why two scenarios differ.

### Non-guarantees that should be stated explicitly

- exact micro-level event-by-event identity across repeated LLM runs
- invariance across different LLM families and temperatures
- invariance across different prompt sets or platform templates
- invariance when scaling from local microblogging runtime to distributed HPC runtime unless specifically validated on matched scenarios

---

## 4. Hypotheses to Test

The paper should define explicit hypotheses.

### Stability hypotheses

**H1. Macro-stability**

Under fixed configuration, repeated runs produce low relative variance in macro observables such as degree inequality, modularity, posting volume, visibility concentration, and opinion dispersion.

**H2. Rank stability**

The relative ordering of experimental conditions is stable across replications. For example, if one recommender yields higher visibility inequality than another, this ordering persists across runs.

**H3. Regime stability**

Repeated runs cluster by configuration rather than mixing across configurations in outcome space.

### Sensitivity hypotheses

**H4. Recommender dominance**

Content recommendation policy is among the strongest determinants of content visibility and engagement concentration.

**H5. Follow policy structural effect**

Follow recommendation policy has stronger effect on final topology than on immediate short-term content volume.

**H6. Opinion parameter effect**

Opinion-dynamics parameters, especially epsilon and theta, strongly affect polarization-related metrics while having weaker direct effect on activity volume.

**H7. Activity effect**

Activity profiles and action-likelihood settings primarily affect posting/commenting volume and secondarily affect topology through follow opportunities.

**H8. Memory path dependence**

Memory increases conversational persistence and repeated interaction, and may increase visibility concentration through social reinforcement.

### Robustness hypotheses

**H9. Infrastructure invariance**

Database backend and Redis acceleration do not substantially change macro outcomes under matched settings.

**H10. Runtime-family correspondence**

Where legacy microblogging runtime and HPC runtime are configured to represent the same scenario class, their macro observables remain close enough to support comparative research claims.

---

## 5. Parameters That Need Controlling

The paper should classify parameters into:

- **primary factors of interest**
- **nuisance factors to control**
- **implementation factors to test for robustness**

### 5.1 Primary factors of interest

These are the main levers whose causal role you want to estimate.

**A. Content recommender**

- `ReverseChrono`
- `ReverseChronoPopularity`
- `ReverseChronoFollowers`
- `ReverseChronoFollowersPopularity`
- `ReverseChronoComments`
- interest/similarity-based methods where available
- random baseline

**B. Follow recommender**

- `Random`
- `CommonNeighbors`
- `Jaccard`
- `AdamicAdar`
- `PreferentialAttachment`

**C. Initial topology**

- Erdős-Rényi baseline
- denser/sparser variants
- homophilic seeded networks
- imported empirical networks where feasible

**D. Agent composition**

- LLM-only
- mixed
- rule-based

**E. Activity and behavior**

- hourly activity curve
- activity profiles
- actions likelihood
- reading-from-followers ratio
- follow probabilities
- churn and newcomer processes

**F. Opinion dynamics**

- disabled
- bounded confidence
- LLM evaluation
- bounded-confidence parameters: epsilon, mu, theta, cold start

**G. Memory**

- disabled
- enabled with lexical/hybrid semantic settings
- search budget and reflection cadence

**H. Topic/news conditions**

- fixed topic seed set
- news/page injection on/off
- topic-shock scenarios

### 5.2 Nuisance factors to control tightly

These should not vary unless a specific experiment studies them.

- number of agents
- simulation duration
- number of slots per day
- prompt set and prompt version
- LLM model identity
- temperature and max token settings
- annotation toggles
- same platform template within each experimental block
- same visibility window
- same database cleanup/startup condition

### 5.3 Implementation factors for robustness checks

- SQLite vs PostgreSQL
- Redis disabled vs enabled
- local browser/desktop orchestration vs HPC path
- single-client vs multi-client
- Ollama vs vLLM for the same model family when feasible

---

## 6. Outcome Variables

The paper needs a metric panel broad enough to cover topology, behavior, and visibility.

### 6.1 Topology metrics

- number of nodes and active nodes
- edge count and density
- in-degree and out-degree distributions
- Gini coefficient of degree
- reciprocity
- clustering coefficient
- assortativity by leaning/archetype/activity
- modularity and community persistence
- giant-component size
- core-periphery measures

### 6.2 Behavioral metrics

- posts per day
- comments per post
- shares per post
- follows created per day
- action mix entropy
- agent-level activity inequality
- churned fraction and newcomer retention
- thread depth and thread longevity

### 6.3 Visibility metrics

- impressions or feed appearances per post if reconstructable from exposure logs
- visibility Gini across authors
- concentration of top-k visible users/posts
- within-group vs cross-group exposure share
- exposure diversity at user level
- exposure novelty over time

### 6.4 Content metrics

- topic prevalence and topic entropy
- sentiment distribution
- toxicity distribution
- emotional diversity
- lexical or semantic diversity
- rate of repeated or near-duplicate content

### 6.5 Opinion metrics

- mean opinion per topic
- opinion variance and bimodality
- polarization indices
- within-community opinion homogeneity
- between-community opinion distance
- time to consensus or stable clustering when relevant

### 6.6 Memory-specific metrics

- repeated-interaction rate
- callback rate across threads
- persistence of pairwise engagement
- community-digest stability
- carryover of high-affect interactions

---

## 7. Experimental Design

The paper should use a staged validation protocol rather than one giant factorial explosion.

### Stage 1. Execution validity

Purpose:

- verify that nominally identical configs produce valid runs
- verify logs and DB outputs are complete
- verify runtime/backend swaps do not break invariants

Tests:

- run canonical scenarios on legacy microblogging runtime and HPC runtime
- verify expected tables, counts, and log artifacts exist
- validate no silent configuration drift

Recommended scenarios:

- 100-agent rule-based baseline
- 100-agent mixed baseline
- 100-agent LLM baseline

Replications:

- 5 per condition is enough here

### Stage 2. Statistical stability under fixed settings

Purpose:

- quantify run-to-run variation

Design:

- choose 4 to 6 representative canonical scenarios
- run each scenario many times

Suggested canonical scenarios:

1. rule-based, reverse chronological, no opinion, no memory
2. LLM-only, reverse chronological, bounded confidence, no memory
3. LLM-only, followers+popularity, bounded confidence, no memory
4. LLM-only, followers+popularity, bounded confidence, memory on
5. mixed population, follow recommender active, bounded confidence
6. HPC-scale mixed population, matched configuration

Replications:

- 30 to 50 runs per scenario if computationally feasible
- at least 20 for the LLM-heavy cases

Analysis:

- coefficient of variation per metric
- intraclass correlation
- bootstrap confidence intervals
- clustering of runs in outcome space
- pairwise distance distributions within and across conditions

### Stage 3. Sensitivity and importance analysis

Purpose:

- identify dominant parameters

Design:

- use a fractional factorial or Latin hypercube style design over major parameters
- alternatively fit a surrogate model over sampled settings

Parameters to vary:

- content recommender
- follow recommender
- topology density
- reading-from-followers ratio
- follow probability
- epsilon, mu, theta
- memory enabled
- activity intensity
- churn probability

Analysis:

- ANOVA or mixed-effects modeling
- Sobol or variance-based sensitivity indices if computationally feasible
- SHAP or feature-importance analysis over surrogate models
- interaction effects, especially recommender × topology and recommender × opinion model

### Stage 4. Robustness to implementation details

Purpose:

- separate scientific effects from infrastructure artifacts

Comparisons:

- SQLite vs PostgreSQL
- Redis off vs on
- one client vs multiple clients
- same scenario on legacy runtime vs HPC runtime where comparable

Analysis:

- equivalence tests on macro metrics
- effect size comparison to primary factors
- confirm infrastructure effects are smaller than major scientific factors

### Stage 5. External plausibility checks

Purpose:

- validate that simulated traces occupy a plausible range relative to known online-platform patterns

This should be framed as **plausibility**, not exact realism.

Candidate comparisons:

- heavy-tailed activity and degree distributions
- visibility concentration
- comment-thread depth distribution
- assortative following by leaning/interests
- temporal activity cycles

Possible empirical references:

- public benchmark social-network datasets
- prior literature on Twitter/Reddit/Bluesky behavioral regularities

---

## 8. Statistical Methods

The paper should combine several methods rather than relying on mean plots.

### Stability quantification

- coefficient of variation
- Wasserstein distance between outcome distributions
- Jensen-Shannon divergence for categorical distributions
- intraclass correlation coefficient
- adjusted Rand index or normalized mutual information for community-structure stability

### Sensitivity quantification

- mixed-effects regression with run as unit
- permutation importance over surrogate models
- Sobol sensitivity indices for selected metrics
- partial dependence plots to show directional effects

### Comparative reproducibility

- rank-correlation of condition means across replication batches
- equivalence tests for infrastructure substitutions
- two-one-sided tests for “implementation-invariant” metrics

### Regime identification

- PCA/UMAP over standardized outcome metrics
- clustering of runs by configuration
- silhouette score to test separation between scenario classes

---

## 9. What to Say About Recommender Roles

The paper should treat recommenders as first-class causal mechanisms.

### Expected role of content recommenders

They likely dominate:

- visibility inequality
- exposure diversity
- engagement concentration
- topic persistence

They likely indirectly affect:

- topology, through differential interaction opportunities
- polarization, through selective exposure

### Expected role of follow recommenders

They likely dominate:

- long-term topology
- assortativity
- community separation
- social reach inequality

They likely indirectly affect:

- visibility through who follows whom
- diffusion potential

### Key design implication

The validation paper should show that recommender policies are not just interface options. They are structural mechanisms that define the simulated social environment.

---

## 10. Recommended Paper Structure

### 1. Introduction

- motivate the need for validation of LLM social simulators
- define the central reliability question
- summarize contributions: stability, sensitivity, robustness, guarantees

### 2. YSocial as a social-simulation stack

- describe `YWeb`, `YClient`/`YServer`, `YSimulator`
- explain platform templates, recommenders, opinion dynamics, memory, and runtime options

### 3. Validation framework

- define execution validity, statistical stability, mechanistic sensitivity, and robustness
- define guarantees and non-guarantees

### 4. Experimental protocol

- canonical scenarios
- factorial/sampled sensitivity design
- replication strategy
- backend/runtime robustness tests

### 5. Metrics

- topology
- behavior
- visibility
- content
- opinion
- memory

### 6. Results

- execution validity
- stability results
- sensitivity results
- recommender role
- infrastructure robustness
- external plausibility checks

### 7. Discussion

- what YSocial reliably supports
- what remains unstable or model-dependent
- implications for future studies using the platform

### 8. Limitations

- dependence on LLM backend
- prompt sensitivity
- realism versus plausibility
- missing human calibration

### 9. Conclusion

- bounded but strong claim on reliability for scenario-level research

---

## 11. Concrete Claim Language for the Final Paper

The strongest defensible final claim is probably:

> YSocial provides a reliable platform for controlled social simulation at the level of scenario regimes: once initial settings are fixed, repeated runs yield stable macro-level outcomes, major behavioral and structural differences are driven by interpretable parameters rather than arbitrary runtime noise, and implementation-level substitutions preserve outcomes within bounded tolerance.

This is stronger and more defensible than:

> YSocial exactly reproduces the same social world every time.

The paper should repeatedly emphasize the distinction between:

- **micro-level stochasticity**
- **macro-level regime stability**

That distinction is the key to scientific credibility.

---

## 12. Minimal Experimental Matrix to Start With

If you need a practical first version of the paper, start with this matrix.

### Block A. Stability benchmark

- 3 population types: rule-based, mixed, LLM-only
- 2 content recommenders: `ReverseChrono`, `ReverseChronoFollowersPopularity`
- 2 opinion settings: disabled, bounded confidence
- memory off
- 20 replications each

Total: 3 x 2 x 2 x 20 = 240 runs

### Block B. Recommender sensitivity benchmark

- fixed mixed population
- 5 content recommenders
- 5 follow recommenders
- bounded confidence on
- 10 replications each sampled combination or a fractional design

### Block C. Robustness benchmark

- choose 4 canonical scenarios
- compare SQLite/PostgreSQL and Redis off/on
- 10 replications per scenario-backend combination

### Block D. Memory benchmark

- fixed LLM-only and mixed settings
- memory off vs on
- 20 replications

This is large but still realistic if staged carefully and if some runs use rule-based or mixed populations.

---

## 13. Deliverables That Would Strengthen the Paper

- public config bundle for all scenarios
- automated metric-extraction notebooks or scripts
- run manifest with seeds, model versions, backend versions, and commit hashes
- confidence intervals and equivalence bounds defined before full execution
- one reproducibility appendix per runtime family

---

## 14. Bottom Line

The paper should not ask whether YSocial is perfectly deterministic. It should ask whether YSocial is a **scientifically reliable generator of controlled online social scenarios**.

If the experiments above work as expected, the paper will be able to support the following conclusions:

- repeated runs are stable at the macro level
- recommender systems are among the strongest determinants of outcomes
- topology, activity, and opinion parameters have interpretable and separable roles
- infrastructure substitutions do not dominate scientific conclusions
- YSocial offers auditable, configurable, and robust support for online social simulation within a clearly stated operating envelope

That is the right validation target, and it is strong enough to underpin several later substantive papers.
