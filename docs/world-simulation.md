# World Simulation: researcher guide

A World Simulation runs several experiments you already have, one per platform (microblogging, forum, photo sharing,
instant messaging, dating), as one simulation: they share a clock, the agents can post on more than one platform, and
their attention, arrival and departure can follow what happens to them across platforms. In the interface the feature
is called **World Simulation**; in the code and in the protocol it is the *federation*.

## Before you start

- Create the experiments first, one for each platform, all with the **same, non-empty population**, the **simulated
  clock** and **hourly** feed refresh (24 slots a day). Two experiments of the same platform type cannot be in the
  same World Simulation, and an experiment can belong to only one.
- Allowed runtimes: forum on the Standard stack; photo sharing, instant messaging and dating on HPC; microblogging on
  Standard or HPC. Remote experiments are not supported.
- Everything is off by default. An experiment that is not part of a running World Simulation behaves exactly as before.

## Create one

Open **World Simulation → New**, choose the experiments (2 to 5), a name, an optional seed and the granularity of the
barrier (`slot`: members stay within one hour of each other; `day`: within one day). Optional mechanisms can be turned
on here or later from the **Configuration** tab of the detail page while the simulation is stopped:

- *Attention*: each agent's day is shared among its platforms according to the stress and reward it had on each.
- *Discovery*: agents who see content cross-posted from a platform may join it.
- *Leave*: agents leave a platform that holds almost none of their attention for several days.
- *Cross-posts*: how a post on one platform reaches the others (see below).

Advanced parameters are a JSON object with the blocks `attention`, `crosspost`, `discovery`, `leave` and `membership`
([reference](reference/world-simulation-configuration.md)).

## Cross-posts

Two modes, chosen with `crosspost.mode`:

- `coordinator_rule` (default): an agent marks a post as one to share (`crosspost_propensity` of the client), and the
  coordinator decides, platform by platform, with the probabilities in `crosspost.probability`. The text is the
  original excerpt.
- `agent_action`: the agent itself decides, for each platform where it also has an account, whether to post there
  (a draw with `crosspost_propensity`) and with which text: a version adapted to the destination, written by the
  language model with the prompts `crosspost_adapt_<platform>` (English and Italian), or the same words shaped and
  cut for the platform when there is no model. The coordinator only checks and forwards. The probabilities in
  `crosspost.probability` are ignored in this mode. The destination platform has to be named like its type
  (`forum`, `microblogging`, ...) for the adapted prompt to be found.

A cross-post sent at a tick is visible on the destination from the next tick. Sending the same message twice has no
effect.

## Run it

The **Execution** tab starts, pauses, resumes and stops the World Simulation as one unit: coordinator, servers,
gateways, clients. While it is starting, running, paused or stopping, its experiments show the *World Simulation* badge
and their own start and stop commands are disabled. When it is stopped, each experiment can be started alone again.
Several World Simulations can be queued from **Schedule**.

## Read the results

The **Analytics** tab shows the share of attention per platform and day, migration between platforms, cross-posts
per day and direction, the cascades of cross-posted contents and survival per platform. The tables can be downloaded
as CSV and recalculated by hand; their columns are listed in
[the analytics mapping](world-simulation-analytics-mapping.md). The per-platform analytics of each experiment
(dating, instant messaging, ...) stay on the pages of those experiments.

## Export, copy, reset

From the detail page:

- **Export** gives one zip: the settings (name, seed, options, members, identity map, SHA-256 of every file), a
  consistent copy of the coordinator database, the analytics, and the archive of each experiment as "Download
  experiment" produces it. The token is not exported.
- **Copy** copies the experiments and creates a new stopped World Simulation with the same seed and options; it starts
  from nothing.
- **Reset** (only when stopped) removes the coordinator database, the analytics and the log. Each experiment keeps its
  own reset.

Importing a bundle back is not available yet: import each experiment with *Upload experiment*.

## Pilot protocol (before a large run)

Run once, with a local model, before an expensive experiment:

1. Three experiments (microblogging, forum and one HPC platform), the same 10 agents, 3 days, a local model such as
   `qwen3:4b-instruct` served by Ollama.
2. World Simulation with `crosspost.mode = agent_action` and a `crosspost_propensity` of your choice, for example 0.2.
3. After the run, compare the share of agent posts that were cross-posted (from the **Cross-posts** analytics divided
   by the posts of the platforms) with the configured value; it is acceptable within ±50% of it.
4. Read a sample of the cross-posted texts on the destination platforms: they must read as posts of that platform
   (length, form, no mention of the other platform).
