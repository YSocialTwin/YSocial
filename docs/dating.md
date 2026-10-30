# Dating experiments

YSocial can run a dating platform next to microblogging, forum, photo sharing and instant messaging: profiles, swipes,
mutual matches, private conversations, dates and exits, with interchangeable matching recommenders. The simulation is
done by the [YDating](https://github.com/YSocialTwin/YDating) runtime, a plugin installed from the **Plugins** page
(group *Dating*). YSocial creates the experiment, launches the YDating server and its clients, monitors them and shows
the result; the simulation and its database (`database_server.db` in the experiment folder) belong to YDating. YSocial
never applies its own schema to that database and never writes to it: it reads it with `mode=ro`, and the only
writes of a person go through the runtime's gateway.

## Create and run an experiment

1. Install the *YDating* runtime from **Plugins**. The platform appears in the experiment form only once it is
   installed. Dating experiments run on SQLite (PostgreSQL is refused) and on the local Ray cluster.
2. Create the experiment and choose *Dating*. On the experiment details page, *Experiment Configuration* has the same
   switches as the other platforms (annotations, stress and reward, memory); the experiment starts locked until
   *Update Configuration* confirms them. *Advanced settings* (page **Dating advanced settings**) shows every key of the
   runtime's `server_config.json` schema as a form with its default, plus the section of the ten recommenders. The
   settings that shape the run lock when the experiment starts; to change them, clone the experiment or reset it.
3. Create a **dating population**. Agents are standard agents (the `agents` table); what is specific to dating
   (location, genders sought, photos, latent variables) is kept in their custom fields, named `dating.*`, and can be
   edited like any custom field. You can upload a file (checked against the population schema of the runtime and
   refused with the path of the problem) or generate a synthetic population from a seed (the same seed always gives the
   same agents). A population page previews the profile card as another user would see it.
4. Create a **client** (population, days, language model, optional advanced settings from the client schema). Before it
   starts, YSocial rebuilds the input file from the database and validates the folder with the offline validator of the
   runtime; a run that would fail to start is refused with the reason.
5. Start the experiment. YSocial starts the server, then (when human participation is on) the gateway, then the clients;
   it stops them in the reverse order. Stop and resume work like on the other platforms and leave no round duplicated.
6. The **Dating LLM Prompts** page shows the prompts the agents use (English and Italian packs), lets you reword them for
   this experiment and records the hash of every prompt with the run.

## What researchers see

The app of the experiment is at `/<experiment id>/dating`. It has three viewpoints, all read-only:

- **Researcher overview** (admin and researcher): everything the run recorded, including private chats, deleted
  messages and the recommender internals (model, score, reason), marked as such.
- **Account** (admin and researcher): exactly what one account could see at a round: its deck, matches, chats and
  notifications.
- **Public observer**: public profiles only, unless the experiment closes it.

Time travel moves any viewpoint to an earlier round; profiles are rebuilt from their change history. Fields reserved
to the researcher never appear in the account and public views (a test fills every reserved field with a marker and
checks that none of them reaches the HTML or JSON of those views).

**Analytics** (page *Dating analytics*, linked from the experiment details): a derived database
(`analytics_dating.db`, rebuilt in full and replaced atomically from the run database) feeds the dashboard: run
totals, each recommender (like rate, matches per stack, Gini of exposure and of likes received), the days, the date
funnel and the exits by cause. Every derived table can be downloaded as CSV, or all of them in one ZIP with the field
map ([dating-analytics-mapping.md](dating-analytics-mapping.md)). *Compare* puts two experiments side by side; the
comparison is clean when population and seed are the same and only the recommender differs.

## Frontend settings

*Dating pages* in the experiment's frontend settings: time travel for viewers, public observer pages, participant mode,
the participant notice (up to 4,000 characters) and the refresh interval of open pages.

## Human participation

Off by default; people play on the same platform as the agents. To use it, set `human.enabled` in the experiment's
*Dating advanced settings* (section *Human participants*: maximum participants, minimum round time, request limits and
which interactions people may use), leave *Participant mode* on in the frontend settings, and assign the users to the
experiment. **A run with human participants is not reproducible**: what happens depends on what the people do and when.
The page *Participants* (linked from the experiment details) says so, shows whether the gateway answers and lists the
people assigned with what each has done.

- **Who can play.** YWeb users with the role *user* or *student* assigned to the experiment, when participation is on.
- **Entry.** The first visit opens a form: the person fills in a profile (name or the pseudonym `participant-<id>`, age,
  gender, who they look for, age range, distance, intent, city, bio, interests, up to three photos, each with a
  description and an optional picture). The runtime validates the profile exactly like an agent's. People start with
  neutral hidden variables. If the researcher wrote a notice, it is shown once before the first entry.
- **The app.** A deck built by the recommender of the experiment (buttons *Pass*, *Super like*, *Like*, arrow keys or
  dragging the card); matches and conversations with replies, reactions, unmatching, date proposals and answers, block
  and report with the runtime's reasons; the person's own profile, preferences, pause and leaving. There is no time
  travel and no other account.
- **Safety.** Every write is `POST` with a CSRF token and goes through the gateway: a loopback address, a per-run token
  (a file with permissions `0600`, never in the state file), request limits and a rate limit. The account is always the
  session's; no request parameter names it. The server checks every rule again: an interaction the researcher switched
  off answers `403` whatever the page shows, and texts and request sizes are limited.
- **Pace.** People never stop the simulation: they act inside the round the agents drive. With *minimum round time* the
  clock waits at least that long while a person is active.
- **Photos.** A person adds or removes photos from *Your profile* (up to `human.limits.max_photos`, 6 by default, 9 at
  most), as the profiles of agents have photos. A photo has a description, which is what the simulated users read, and
  optionally a picture: PNG, JPEG or WebP up to 5 MB, checked by content (the name and declared type do not count),
  decoded and re-encoded so that metadata and anything appended to the file are dropped, and stored in the `media`
  folder of the experiment under a name made for the account. Pictures are served only from that folder, to the
  people who can open the dating pages of the experiment. A removed photo stays in the database (and its file on disk)
  so that time travel can still show it.
- **Profile views.** Opening the profile of another account (from the deck, a match or a chat) is recorded in the
  run database as a profile view (`profile_views`: viewer, profile, source, round, once per round). Only profiles the
  person can see are recorded. The deck itself is recorded as exposure, as for any agent.
- **Offline.** While the server is stopped a person can do everything they can do online (deck, swipes, chat, dates,
  photos, profile, pause, leaving): a short process loads the world from the database for each request, under a file
  lock, and acts in the round at which the experiment stopped. The stack they were shown and the likes used today are
  rebuilt from the database, so the daily quotas hold. Before the experiment has run a round there is nothing to
  play: the pages answer that the experiment has not started yet. Notifications are not kept between requests.

## Limits

- SQLite only; one local Ray cluster; no remote dating experiments.
- Default rates of the runtime (for example the share of agents that leave as couples) are not calibrated: see the
  YDating documentation before comparing figures with the literature.
- Italian texts of the interface are a draft until a native speaker reviews them.
