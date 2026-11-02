# World Simulation: researcher guide

A World Simulation runs several experiments you already have (microblogging, forum, photo sharing, instant messaging,
dating; several of the same platform are fine), as one simulation: they share a clock, the agents can post on more than one platform, and
their attention, arrival and departure can follow what happens to them across platforms. In the interface the feature
is called **World Simulation**; in the code and in the protocol it is the *federation*.

New to the idea? Start with the [plain-language overview](world-simulation-overview.md).

## Before you start

- Create the experiments first (2 to 8), with a **non-empty population** in at least one of them, the **simulated
  clock** and **hourly** feed refresh (24 slots a day). Several experiments of the same platform type can be in the
  same World Simulation (two microblogging experiments and a forum, say); an experiment can belong to only one World
  Simulation, and can be chosen only once.
- Member names: with one experiment per platform type the members are called as the platform (`microblogging`, `forum`),
  exactly as before. When a type appears more than once, each member of that type is called `<platform>-<experiment id>`
  (`microblogging-3`): it does not change when the experiment is renamed and it is the name used in the generated files
  (`bindings_<member>.db`, the configuration sections) and in the probability pairs (`microblogging-3->microblogging-7`).
  The pages show the experiment name. In the probability table every ordered pair of experiments has its own cell
  (default 0.3); a stored pair of platform types (`microblogging->forum`) is the default for every pair between those two
  types, and an exact pair of members always wins. The same agent has one account on each experiment of the same type.
- Allowed runtimes: forum on the Standard stack; photo sharing, instant messaging and dating on HPC; microblogging on
  Standard or HPC. Remote experiments are not supported.
- Everything is off by default. An experiment that is not part of a running World Simulation behaves exactly as before.
- The World Simulation needs the **optional YFederation plugin** (the folder `external/YFederation`, the `ysocial_federation`
  package). It is not a pip dependency. Without it YSocial works as before for every classic experiment: the
  *World Simulation* menu entry is hidden, its pages answer "The YFederation plugin is not installed" instead of an error,
  and profile badges and cross-post options do not appear. Install the plugin and reload the page; nothing else has to be
  restarted. When you start a World Simulation YSocial first checks that the plugin can be imported, and also that the
  servers and clients of the members (which run as their own processes) can import it; if not, the start stops with the
  reason and nothing is launched.

## Create one

Open **World Simulation → New**. The page is one form in numbered sections; every parameter is a field with its default
already filled in, so a World Simulation can be created by choosing the members and a name. The same sections are on the
**Configuration** tab of the detail page, editable while the simulation is stopped. There is no JSON to write.

1. *Basics*: the name, an optional description and seed, and the members: pick the experiments (2 to 8 in all, several
   of one platform type if you like) that take part, each shown with its populations. The matrices below (probability
   of each pair, starting probability) list the chosen experiments by their names.
2. *Clock and schedule*: the granularity of the barrier (`slot`: members stay within one hour of each other; `day`:
   within one day).
3. *Attention*: each agent's day is shared among its platforms according to the stress and reward it had on each
   (window, temperature, inertia, floor and the other limits), and the *Leave* rule: agents leave a platform that holds almost
   none of their attention for several days (it needs attention to be on).
4. *Discovery*: agents who see content cross-posted from a platform may join it (decay, thresholds, quoted weight and, under
   *Advanced*, the weights per platform type).
5. *Cross-posting*: the mode, the **propensity** and the probability from each platform to each other one (defaults 0.2 and 0.3), which agent content can travel
   (all content by default, or the kinds you add: the agent's own content, content with news, content with images) and
   whether authors are shown with a pseudonym.
6. *Identity and populations*: how agents are present on the members (initial membership: all, one random member, or a
   chosen fraction per platform), topic migration and, for microblogging, whether the members are provisioned.
7. *Humans*: the users enrolled (see below).
8. *Advanced*: collapsed by default, with the less common values filled in.

A value left blank is not written and the default applies; a value equal to the default is not saved either, so the
`federation.json` of a simulation that changes nothing is the same as before. Values outside the allowed range are
refused with a message naming the field. Settings stored by another release that the form does not know are kept as
they are when you save, and are listed under the form. **Show the generated file** on the detail page displays the
resulting `federation.json` read-only. The values are described in the
[reference](reference/world-simulation-configuration.md).

## Cross-posts

Two numbers drive the cross-posts, both set in the **Cross-posting** section of the form (creation page and the Configuration
tab of the detail page):

- **Propensity to cross-post**: the probability that an agent marks a post it publishes for cross-posting. It is a random draw,
  not a decision of the language model. YWeb default **0.2**.
- **Probability of a cross-post for each pair of platforms** (the matrix, *From* the row *To* the column): in `coordinator_rule`
  mode, the chance that a marked post is copied from the source to the destination platform. YWeb default **0.3** for every
  ordered pair of member platforms.

These are the YWeb defaults: they are written explicitly into the member configurations and `federation.json`, so the
coordinator's own defaults (0 for both) are never relied on. A World Simulation stored without them (for example one created
before this default) gets them at its next start; a value you stored, **an explicit 0 included**, is always kept. Set 0 on
purpose to switch cross-posting off for everyone or for a pair (the form then warns that no cross-post can happen).

Two modes, chosen with `crosspost.mode`:

- `coordinator_rule` (default): an agent marks a post as one to share (`crosspost_propensity` of the client), and the
  coordinator decides, platform by platform, with the probabilities in `crosspost.probability`. The text is the
  original excerpt.
- `agent_action`: the agent itself decides, for each platform where it also has an account, whether to post there
  (one random draw per destination platform with `crosspost_propensity`; the model does not decide) and with which text: a version adapted to the destination, written by the
  language model with the prompts `crosspost_adapt_<platform>` (English and Italian), or the same words shaped and
  cut for the platform when there is no model. The coordinator only checks and forwards. The probabilities in
  `crosspost.probability` are ignored in this mode. The destination platform has to be named like its type
  (`forum`, `microblogging`, ...) for the adapted prompt to be found.

A cross-post sent at a tick is visible on the destination from the next tick. Sending the same message twice has no
effect.


### Who decides whether to cross-post

By default a **random draw** decides, using the propensity above. In the Cross-posting section, *Who decides whether to cross-post* can be set to *The agent decides (LLM)*: then each agent asks its own language model, once per event, whether the content is worth posting elsewhere (and, in the *agent_action* mode, where and with which words). You choose the events that trigger the question (the agent publishes a post; the agent shares, comments, replies or reacts) and the maximum number of questions per agent per day (default 5; over the cap the random draw is used). Costs: **one extra model call per event** that is asked, so a large population can add many calls; rule-based agents, content that is not eligible and platforms with no other destination cost nothing. If the model does not answer in time or answers badly, the random draw is used instead and the run goes on; in this mode the propensity only serves as that fallback. Runs with LLM decisions are not reproducible from the seed. The form lists the member platforms that support the option; the others keep the random draw. Each decision is written in the client log (`federation decision ...`). It is read at start, so change it while the simulation is stopped.
### Which content can be cross-posted

By default **all content** can be cross-posted: the agent's own and that of other agents (shares, replies, forwards). In the
**Configuration** tab (and in the new-simulation form) *Agent content that can be cross-posted* has the first option
*All content (the agent's own and that of other agents)*, ticked by default. Untick it to choose instead the kinds of
content to **add**, in both modes:

- *The agent's own content*: what the agent wrote itself (a post, a comment, a message, a photo); shares, reshares and
  forwards of other people's content are not own content;
- *Content with news (a link)*: any content, the agent's or another's, that links a news article (or has an `http(s)://`
  address in its text);
- *Content with images*: any content with an image.

The options **add up**: content is eligible when it fits at least one chosen option, so choosing more never reduces what can
travel. Own content and news is "the agent's own content plus any content with a link". At least one choice is required (the
page refuses an empty choice), and *All* excludes the others. Content that is not eligible stays on its platform and is
recorded as `crosspost_filtered` (reason `not_eligible`, with the chosen options) in the event log of the coordinator; nobody
waits for it. People who take part are never filtered, because they choose what they share. The setting is read when the World
Simulation starts, so edit it while the simulation is stopped and start it again; while it runs the page shows the saved value
and it cannot be changed. It is saved in `crosspost.content` (`["all"]`, or a list of `own_content`, `news`, `images`;
`own_posts` is the legacy name of `own_content` and is still accepted), exported with the simulation and copied by *Copy*; a
simulation created before the option existed behaves as "all". A list of two or more entries saved by the first version of
this option (which combined them with AND) now reads as OR. Agents are offered the cross-post of something they share only
when it can be eligible. Forum and microblogging runtimes pass the article link of news content; on the other platforms a
link counts only if it is in the text.

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

### Open the member experiments in the browser

An experiment can be opened from the web only while it is *active* (the **Activate** switch of the experiments page). A World
Simulation can activate the web interface of all its members for you:

- When it starts, unless you switch off *Activate the web interface of the member experiments when the simulation starts* (a
  field of the form, on by default). It is done before the servers start; a member that cannot be activated is reported as a
  warning and the start goes on.
- With the **Activate frontends** and **Deactivate frontends** buttons of the Execution tab, in any state of the World
  Simulation. The same box lists each member with *Active* or *Inactive* and an **Open** link for the active ones. Pressing a
  button twice changes nothing; members of experiments you may not see are skipped with a message.

Stopping the World Simulation does **not** deactivate the experiments: use **Deactivate frontends** when you want to close them.
Instant messaging and dating members get the same access row as with the single switch (they keep their own database).

### Is every member alive? (health of a running World Simulation)

While the World Simulation is running, the **Execution** tab (and the list page) watch the members, using only what the
coordinator and YSocial already know:

- A **Health** badge for each member: *OK*, *Waiting for X* (it is ahead and waits for the slowest member), *Starting*,
  *Missing*, *Stalled*, *Not running*, *Failed*, *Finished*.
- A **banner** on top lists the members in trouble, with the probable cause when the end of the member's log shows one
  (for example `Python module 'ysocial_federation' not found`, `connection refused`, `the port is already in use`) and the
  log file to open.
- A **progress line**: `Tick 3/720, ~65 s per tick, ETA 13 h`. The time per tick is the median of the recent advances of
  the shared clock, so a slow LLM run is not mistaken for a stuck one. Ticks are hours; the total is the longest client
  (days x 24).

Definitions:

| State | Meaning |
|-------|---------|
| Missing | the member did not say *hello* to the coordinator within 60 s of the start of the run |
| Stalled | no new *ready* for max(120 s, 5 x the median tick time) **while the other members wait for it** |
| Not running | the server process of the member exited, or all its clients did (one of several clients is also reported) |
| Waiting for X | not a problem: the member is ahead and the gate holds it until X catches up |

A run where every member is equally slow is not reported as stalled (nobody is waiting); use the tick time and the logs.

### Troubleshooting

- **"The YFederation plugin is not installed"**: the folder `external/YFederation` is missing or `ysocial_federation` cannot be
  imported by YSocial. Install the plugin; classic experiments are not affected.
- **The start fails with "cannot import the YFederation plugin"**: the processes of the members could not import it. The
  message carries the Python error; check the interpreter YSocial runs with and the `PYTHONPATH` of the members.
- **A member shows *Missing* or *Not running***: open the log named in the banner. For a server it is `server_stderr.log` in
  the folder of the experiment, for a client `<client name>_client_stderr.log` in the same folder. The usual causes are a
  missing Python module, a port already in use, or a database that cannot be opened. Stop the World Simulation, fix the
  cause and start it again: it resumes from where it stopped.
- **A member shows *Stalled***: it is slower than the others or blocked (for example a language model that does not
  answer). Check its client log and the model server; the other members wait for it.
- **Everything looks stuck but nobody is flagged**: check the time per tick in the progress line. With a large language
  model one tick can take minutes; the ETA is computed from it.
- **The banner says the coordinator does not answer**: read the *Coordinator log* below the table.

#### No cross-posts appear

The Execution tab shows a **Cross-posts** line: how many cross-posts the coordinator has materialised (and in how many ticks)
and how many contents were exported to it. When the run is past tick 6 with nothing exported and nothing materialised, a notice
gives the probable cause. It is not an error: it happens when the propensity or every probability was set to 0 on purpose or by mistake.

- **Propensity 0** (`crosspost.propensity`, YWeb default 0.2, written as `crosspost_propensity` in the members; the SDK default is 0): no
  agent marks a post for cross-posting (by rule) or posts on another platform (by agent action), so no content is exported.
- **Every probability 0** (`crosspost.probability`, YWeb default 0.3 for every pair, SDK default 0; rule mode only): content is exported, but the
  coordinator copies it to no platform. The probability is given for each pair, e.g. `microblogging->forum`.

The form warns while you type (Cross-posting section) and the detail page repeats the warning for the saved values. Set the
propensity (the share of posts the agents mark for cross-posting) and the probability for at least one pair of platforms; an
empty field takes the default (0.2 and 0.3). Lower them for large populations. If both are set and still nothing is exported, check the content filter (*Agent content that can be cross-posted*)
and that the agents are posting (the *Events* list shows `crosspost_filtered`).

#### One member cross-posts, another never does

If the clients of a World Simulation run from a version older than the fix `[MP-U3.1..3]`, the **microblogging** client did not
switch the federation on in its own process (the forum client did), and the loop that YWeb runs for the microblogging and the
forum did not apply the attention multipliers, the membership filter or the adoption of provisioned accounts. The signs: in
agent-action mode the server log shows `GET /federation/destinations` for one member only, one member exports no content, the
attention multipliers have no effect, and agents that left a platform keep acting on it. Update YSocial and its clients and
**stop and start the World Simulation** (clients read the configuration at start; a resume continues from where it stopped, the
data already produced is kept).

### Who is active where (Agents tab)

The **Agents** tab of a World Simulation lists every agent and enrolled person with one state per platform: *active*,
*dormant* (the account exists but has not joined or been discovered), *left*, *ineligible* or, before the first run, *not
started*. A summary table counts the states per platform, the list can be filtered by name, platform, state and kind, and
**Download agents (CSV)** exports one line per account with the ticks of joining and leaving. The states are read from the
coordinator's database, read-only; `membership.initial` decides who starts active.

Next to the states, three **cross-posting columns** count what each agent did, from the `crosspost.v1` messages of the
coordinator's database (one grouped query per metric; a missing table shows `-`):

- **Own cross-posts**: cross-posts the agent made, as the author, of its own content (a `crosspost.v1` message whose
  `global_agent_id` is the agent and that has no `quoted`; one per destination).
- **Shares**: cross-posts it made of other agents' content (the same, with `quoted`).
- **Cross-posted**: delivered copies of its own content (own cross-posts that have a row in `federation_delivery`); hover
  for the count per destination experiment, click to open the Cross-posts tab filtered on the agent.

Both cross-posting modes are counted: with `coordinator_rule` the coordinator materialises the `crosspost.v1` messages
with the author's id, with `agent_action` the agents emit them. The columns are sortable (click the header), the list can
be filtered by cross-posting activity, and the CSV carries `crossposts_own`, `crossposts_of_others`,
`times_crossposted` and `times_crossposted_by_destination`.

### Cross-posted contents (Cross-posts tab)

The **Cross-posts** tab lists the contents copied from one experiment to another, one row per content and destination:
the tick (day and slot), the author (a link to the profile on the origin frontend), the origin and destination
experiments as icons, a text excerpt, the mode (`agent_action` or `coordinator_rule`) and whether it was delivered or is
still pending. The icon is the platform type and its tooltip the experiment name; it links to the content itself on that
experiment's frontend (`/<exp>/thread/<post>`, `/<exp>/rthread/<post>`, photo, IM) when the experiment is **active**, and is
shown dimmed, with the reason in the tooltip, otherwise. The origin content comes from the `source_ref`
(`ysocial://<federation>/<member>/post/<id>`), the copy from the `federation_ref` of the destination database (by
`fed_msg_id`, otherwise by `source_ref`).

The table is searched and paged on the server and everything is in the address (GET): `q` (text excerpt or author name), `source`
and `destination` (members), `agent`, `status` (`delivered`/`pending`), `mode`, `tick_from`/`tick_to`, `sort`
(`tick_desc`/`tick_asc`), `size` (25, 50 or 100) and `page`. **Download cross-posts (CSV)** exports the same filter (at most
20,000 rows). The coordinator's database is read-only and owns its indexes, so the queries filter by message type and are
bounded by the page size, an offset limit and a capped total. The "Cross-post cascades" table of the Analytics tab links each
original content to this tab (`ref=`).

### Profile badges

On the profile page of an agent (or of an enrolled person), every platform shows one badge for each *other* platform of the
World Simulation where the same identity has an account; it links to the profile there. An agent that is dormant or has left
a platform is not shown on it, and the badges come from the coordinator's database, read-only. Pages outside a World
Simulation are unchanged.

Platforms are always named after their **experiment** (for instance *XW* or *FW*), never after their type: the badges, the
"Cross-posted from / to" back-links, the "Shared from" attribution, the notice of cross-posts waiting for a stopped platform
and the "Also post on" chooser all use `Exps.exp_name`, and the platform type is only the icon. They are keyed by member, so a
World Simulation can hold several experiments of the same type.

### Back-links of cross-posted content

A post, photo or message that was cross-posted shows where it comes from: "Cross-posted from <platform> · @author", with a
link to the original (for example a microblogging post copied from the forum links to `/<exp>/rthread/<post>`). On the
original, "Cross-posted to <platform>" lists one link for each copy. A link is shown only while the web interface of the
other experiment is active and the content still exists; otherwise the platform is named without a link. The data are the
`federation_ref` tables of the member databases, read-only and once per page; a quoted share keeps its own "Shared from"
block, and content that was never cross-posted is unchanged. Photos link to the author's profile (a photo has no page of its
own) and dating shows no card for cross-posts.

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


## Flexible populations (INV-17, INV-18, INV-19)

Clients of a World Simulation may have disjoint or partly overlapping populations. Identity is bound by user name: the runtime reports each account, the coordinator assigns the global id (`Agent.id`) and the runtime never falls back to its local id (INV-17). Agents and clients added while the simulation runs are active at the current tick and keep full action rates (INV-18). An agent may discover a platform where it was not deployed: the coordinator records `provision_requested`, the runtime creates the account at the next day start (member option `provision`) and binds it, and the agent becomes `active` (INV-19). Specification: `external/YFederation/docs/flexible-populations.md`.
