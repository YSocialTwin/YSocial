# World Simulation: researcher guide

A World Simulation runs several experiments you already have, one per platform (microblogging, forum, photo sharing,
instant messaging, dating), as one simulation: they share a clock, the agents can post on more than one platform, and
their attention, arrival and departure can follow what happens to them across platforms. In the interface the feature
is called **World Simulation**; in the code and in the protocol it is the *federation*.

New to the idea? Start with the [plain-language overview](world-simulation-overview.md).

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

### Shared content shows its origin

When an agent shares, on one platform, content written by another agent and the share is cross-posted to a member, the
receiving platform writes the post with a line at the end (`↪ author @ platform: «excerpt»`) and keeps the structured
reference in its own `federation_quoted` table. The pages of the member experiments (microblogging and forum feeds and
threads, photo feed, instant-messaging chats) show it as a small block above the post: *Shared from <author> on
<platform>* with the excerpt. Nothing is shown for posts without a quotation, dating shows no posts, and an experiment
that is not part of a World Simulation never reads the table. The pages read it read-only from the experiment's server
database (`database_server.db`), so a deployment that keeps the experiment databases elsewhere shows no block.

## Participants (people)

A person (a YWeb user) can take part in a World Simulation next to the agents. In the **Configuration** tab, section
*Participants*, pick the user and the platforms to enrol them in. Each enrolment:

- gives the person the identity `human:<user id>` (the same in every World Simulation) and **one account on each platform you
  ticked**; they can cross-post only to platforms where they are enrolled;
- creates the account through the platform's *gateway* (YWeb never writes the databases of the runtimes): instant
  messaging, dating, microblogging, forum and photo sharing each have one, and it also works with the server stopped. On the
  HPC backend (YSimulator, microblogging) the gateway is a script of the runtime, `run_human_gateway.py`, that works with the
  server running or stopped;
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

### Who is active where (Agents tab)

The **Agents** tab of a World Simulation lists every agent and enrolled person with one state per platform: *active*,
*dormant* (the account exists but has not joined or been discovered), *left*, *ineligible* or, before the first run, *not
started*. A summary table counts the states per platform, the list can be filtered by name, platform, state and kind, and
**Download agents (CSV)** exports one line per account with the ticks of joining and leaving. The states are read from the
coordinator's database, read-only; `membership.initial` decides who starts active.

### Profile badges

On the profile page of an agent (or of an enrolled person), every platform shows one badge for each *other* platform of the
World Simulation where the same identity has an account; it links to the profile there. An agent that is dormant or has left
a platform is not shown on it, and the badges come from the coordinator's database, read-only. Pages outside a World
Simulation are unchanged.

### Posting on several platforms (people)

Where a person is enrolled on more than one platform, every composer shows *Also post on* with one box per **other**
platform where they are enrolled (nothing is shown to anybody else). Tick the platforms and publish:

- the post goes through the gateway of the platform (microblogging: post and share; forum: new thread; photo sharing: new
  photo and share; instant messaging: message and forward; dating: accepting a date, unmatching, ignoring, messages and
  replies) with `crosspost_to`, the same field the agents send, so it leaves at the next barrier and arrives once;
- the text on each destination is the person's own, shaped for it with a plain rule (a title for a forum, the limit of each
  platform); no language model is involved. Ticking a platform opens a text box under it, **prefilled with that rule's
  text** (the page asks the server for it, `GET /<exp>/federation/crosspost_suggest`, so the rule lives only in
  `human_outbox.py`) and refreshed while the person types, until they edit it. The person can change the text for each
  destination; it is limited to the platform's limit, an emptied box goes back to the rule text, and the page sends only the
  edited texts (`crosspost_texts`). The server never trusts the page for *where* the post goes: it recomputes the
  destinations (enrolled members only) and cuts every text to the platform's limit;
- sharing another's content carries the original author as `quoted`, with the author's local name;
- the forum composer keeps its *community* selector: the community is resolved to a topic of the forum server
  (`GET /get_topics`) and sent as `community` on the gateway action, so the thread lands in that community; if the forum
  server cannot be reached, or the community is not a topic there, the thread goes to the default community;
- dating: a private message or reply is **never** shared by itself. The dating composer has a separate *Share how the date
  went* choice (we keep seeing each other, they ghosted me, it didn't work out) plus a text in the person's own words;
  only then the message action carries `story: {"event": ...}` together with `crosspost_to`. Accepting a date, unmatching
  and ignoring keep their own story events;
- limits: a post that carries a link or an image link keeps the direct path, because the microblogging and forum gateways
  have no link support: the *Also post on* boxes are hidden while a link is filled and nothing is cross-posted; a person
  who ticks nothing posts exactly as before. With the server stopped the request is recorded and leaves at the first
  barrier after the restart; a person on a stopped platform sees what others cross-posted to it only after it restarts.
- **cross-posts waiting for a stopped platform**: when the World Simulation runs but the platform of an enrolled person is
  stopped, the composer area shows *N cross-posts are waiting and will appear when this platform restarts* with the text of
  each (and the `↪ author @ platform: «excerpt»` line of a share). It reads the coordinator's read-only `GET /v1/pending`
  (nothing is acknowledged), is cached for a few seconds, and makes no request at all for anybody who is not enrolled, when
  the World Simulation is not running or the platform's server is up. Any error just hides the notice. It shows exactly what
  the endpoint returns: with `crosspost.mode = coordinator_rule` a cross-post that has not been materialised yet is not in
  the answer, so it is not listed either;

## Read the results

The **Analytics** tab shows the share of attention per platform and day, migration between platforms, cross-posts
per day and direction, the cascades of cross-posted contents and survival per platform. The tables can be downloaded
as CSV and recalculated by hand. When agents share the content of other agents across platforms
(`crosspost.mode = agent_action`), the tab also shows the depth of the share chains, the bridge agents (who carries
content from one platform to another) and the topics that travelled with cross-posted content. *Topic diffusion* lists,
per topic, the platforms where it appeared, how many cross-posts carried it, the platforms that created it on arrival and
the first and last day; *Topics created on arrival* lists what each destination actually created (and the original name when
it had to be shortened). The creations are read, read-only, from `federation_topic` and `federation_topic_origin` in the
member databases; if a database cannot be reached the tables fall back to the coordinator-only data (what travelled, with no
creations). The first tick of each topic on each platform is in the CSV `topic_first_seen`. The staleness check of the derived
database looks at the coordinator database only, so a creation that happens after the last cross-post shows up at the next rebuild. The *People* table lists what each person did across platforms (cross-posts and shares, platforms of origin and reached,
first and last day; people are told apart by the `human:` prefix of their identity, which agents never use). The tables of the tab and their columns are listed in
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

A longer protocol, covering shares with attribution, topics, quoted content, pseudonyms and people, is in [World Simulation pilot](world-simulation-pilot.md).
