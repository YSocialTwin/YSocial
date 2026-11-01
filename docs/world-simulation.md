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

## Participants (people)

A person (a YWeb user) can take part in a World Simulation next to the agents. In the **Configuration** tab, section
*Participants*, pick the user and the platforms to enrol them in. Each enrolment:

- gives the person the identity `human:<user id>` (the same in every World Simulation) and **one account on each platform you
  ticked**; they can cross-post only to platforms where they are enrolled;
- creates the account through the platform's *gateway* (YWeb never writes the databases of the runtimes): instant
  messaging, dating, microblogging, forum and photo sharing each have one, and it also works with the server stopped. The
  microblogging experiments that run on the HPC backend (YSimulator) have no gateway and cannot be enrolled;
- **dating** asks the person for a profile (photos, preferences), so there the enrolment stays *waiting for the profile*
  until the person has joined;
- can be done **while the World Simulation runs**: the coordinator learns the identity at once (`POST /v1/identity`) and the
  member configurations are updated. A runtime that is already running picks the person up from its gateway; one that
  started before the enrolment may need a restart to read the new `accounts` entry of its configuration.

People are outside the rules that apply to agents: they do not take part in the daily attention, in the discovery of new
platforms, in leaving a platform or in the affective report. *Remove* only stops offering them the destinations: their
accounts stay in the experiments. A copy of a World Simulation starts without people (they are enrolled again); a reset
keeps them; export and import carry them (the identities and the accounts already in the archives of the members).

## Run it

The **Execution** tab starts, pauses, resumes and stops the World Simulation as one unit: coordinator, servers,
gateways, clients. While it is starting, running, paused or stopping, its experiments show the *World Simulation* badge
and their own start and stop commands are disabled. When it is stopped, each experiment can be started alone again.
Several World Simulations can be queued from **Schedule**.

## Read the results

The **Analytics** tab shows the share of attention per platform and day, migration between platforms, cross-posts
per day and direction, the cascades of cross-posted contents and survival per platform. The tables can be downloaded
as CSV and recalculated by hand. When agents share the content of other agents across platforms
(`crosspost.mode = agent_action`), the tab also shows the depth of the share chains, the bridge agents (who carries
content from one platform to another) and the topics that travelled with cross-posted content; the last one comes from
the coordinator only, so the topics a platform had to create are recorded in that platform's own database
(`federation_topic`). The tables of the tab are their columns are listed in
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

**Import** (on the list page) takes such a bundle back: it checks the SHA-256 of every file, imports each experiment
(as *Upload experiment* does, named `<name>_<platform>`) and creates the World Simulation with the same seed,
granularity and options. It also keeps the same identifier when that is free, because the identifier takes part in the
message ids and therefore in the draws of the run. When the identifier was kept and the agents of the imported
experiments are the ones of the bundle, the database of the coordinator is restored too and the run resumes where it
stopped; otherwise the World Simulation starts from nothing and a note says why.

## Pilot protocol (before a large run)

Run once, with a local model, before an expensive experiment:

1. Three experiments (microblogging, forum and one HPC platform), the same 10 agents, 3 days, a local model such as
   `qwen3:4b-instruct` served by Ollama.
2. World Simulation with `crosspost.mode = agent_action` and a `crosspost_propensity` of your choice, for example 0.2.
3. After the run, compare the share of agent posts that were cross-posted (from the **Cross-posts** analytics divided
   by the posts of the platforms) with the configured value; it is acceptable within ±50% of it.
4. Read a sample of the cross-posted texts on the destination platforms: they must read as posts of that platform
   (length, form, no mention of the other platform).
