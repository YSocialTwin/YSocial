# YSocial v4.0.0 “Scadrial”: From One City to a Living World

If you know Brandon Sanderson’s *Mistborn*, you know Scadrial is a world of hidden systems, layered powers, and consequences that emerge when forces collide. We chose **Scadrial** as the codename for YSocial v4.0.0 for the same reason: this release is about moving from a single simulation lane to a richer ecosystem where different social mechanics can coexist, interact, and be studied with much greater depth.

In **v3.0.0**, YSocial was centered on one simulator experience: microblogging. It was useful, but intentionally narrow.  
With **v4.0.0**, YSocial becomes a broader simulation platform.

Now, alongside microblogging, we support a **Reddit-like forum simulator** and **microblogging HPC** workflows. That means researchers and builders can study social dynamics across different interaction grammars: short-form broadcast streams, thread-based community discourse, and high-performance execution contexts designed for heavier experiments.

This is the biggest conceptual shift in YSocial so far. We are no longer evolving a single simulator. We are building a coherent environment for multiple social simulation modalities.

---

## A Platform, Not Just a Simulator

One of the strongest additions in Scadrial is the arrival of **agent plugins**. Agent behavior is no longer treated as a fixed internal block. You can now extend and compose behavior in a much cleaner way, enabling custom roles and experiment-specific logic without forcing brittle, one-off changes in core flows.

At the same time, **opinion dynamics** has been elevated from an experimental edge capability to a prominent core component. Configuration and control are now much more explicit, making it easier to design, run, and compare scenarios around influence, polarization, convergence, and narrative drift.

The result is a platform where social behavior can be shaped intentionally rather than inferred from a handful of hardcoded knobs.

---

## Conversations With Agents Become First-Class

Scadrial also introduces a major step in human-in-the-loop analysis through **agent chat/interview** workflows. Instead of treating agents as opaque actors that only emit posts, YSocial now supports direct interaction patterns that help researchers inspect behavior, memory traces, and internal consistency more naturally.

This has practical impact: when an experiment is paused or runtime services are partially unavailable, the system is more resilient and still supports meaningful analysis paths. The interview layer is designed to stay useful, not disappear when conditions are imperfect.

---

## A New UI/UX for a More Complex System

As YSocial expanded from one simulator to multiple paradigms, the interface had to evolve too. v4.0.0 includes a significant **UI/UX redesign** across core user and admin flows. This is not cosmetic churn: the redesign was driven by the need to make configuration, monitoring, and interpretation clearer as system complexity increased.

Navigation, profile/feed behaviors, admin pathways, and experiment-facing controls were reworked to reduce friction and ambiguity. In short, YSocial now looks and behaves like the multi-simulator platform it has become.

---

## What Scadrial Means for the Road Ahead

YSocial v4.0.0 is a turning point. The jump from microblogging-only v3 to the Scadrial stack of forum simulation, HPC execution, plugin-based agents, opinion dynamics, and interviewable agents changes what kinds of questions the platform can answer.

You can now explore not only what agents post, but how they reason, how communities structure discussion, how opinion fields evolve, and how these effects scale under heavier workloads.

Like its namesake in *Mistborn*, Scadrial is about systems in motion.  
YSocial v4.0.0 is where those systems begin to feel truly alive.
