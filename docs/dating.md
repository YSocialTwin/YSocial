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
   *Update Configuration* confirms them. **Experiment settings** (page *Dating settings*) holds what is shared by every
   client: the recommender (with the parameters of the selected model), the daily quotas, time and start, the rules
   of chats and dates, and the rules of stress and reward. Human participation needs no setting: people can always
   take part next to the agents (see *Participants*). Each section says what it does and each
   setting has a readable label and a hint. Settings that already live in the Experiment Configuration (memory,
   embedding model, annotations) are not repeated; a section whose switch is off says so and links there. The
   page is a single form with tabs (Recommender, Time and quotas, Chats and dates, Other settings) and one **Save**
   for all of them; choosing a recommender shows its description on the right, the switch *Only show profiles within the distance* (off by default: the declared distance still counts for the models that use it but never removes a candidate) sits in the same tab, and the rarely needed parameters sit
   in *Advanced parameters* panels that are closed until opened. The settings can be edited whenever the experiment is not running; once it has produced data the slot length and the
   seed stay fixed.
3. Create a **dating population**. Agents are standard agents (the `agents` table); what is specific to dating
   (location, genders sought, photos, latent variables) is kept in their custom fields, named `dating.*`, and can be
   edited like any custom field. You can upload a file (checked against the population schema of the runtime and
   refused with the path of the problem) or generate a synthetic population from a seed (the same seed always gives the
   same agents). Every agent lives in a city of its own nationality (the catalogue has the main cities of each of the 54
   nationalities; a city line may name the nationality that lives there). A population page previews the profile card
   as another user would see it.
   Dating populations are created in the same form as those of the other platforms (Admin > Populations: choose the
   platform **Dating**, available only when YDating is installed; the same applies to *Load Population from file*).
   Name, size, nationality, spoken language, age classes, gender, education and political leaning use the same
   selectors, with percentages that total 100, as the other platforms; the Dating sections add the intent, the genders
   sought by women and by men, appearance, latent variables, affective traits and the daily activity level, each with a
   proposed default. The daily rhythm of the agents is set here too, with the **activity profiles** (Always On, Night
   Owl...) of the other platforms, assigned with percentages; they are the dating equivalent of the archetypes. Personality, cities and distances and interests are sampled by the generator. The recommender is
   chosen in the client (section *Recommender*), not for each individual.
   Ad hoc agents can carry the same variables: the **Dating** section of Admin > Agents (also shown only when YDating
   is installed) stores them as `dating.*` custom fields, which the other platforms ignore; assign the agent to a
   dating population to use it in a dating simulation.
4. Create a **client**: choose the population and the duration (30 days; *Run until stopped* keeps it running), then
   the models in this order: the language model (address, *Fetch* the models, choose one, as on the other platforms),
   the image model (vision model and the model that draws the profile photos, either photorealistic human faces or
   fantasy cartoon characters; the drawing model is chosen from a short list of small models of the Hugging Face hub,
   *tiny-sd* by default, or any other diffusers model id, downloaded on first use) and the recommender, which is chosen per client (each model is explained on the page;
   the default is the one of the experiment settings). The defaults follow the experiment: with language models the
   agents use them for everything (texts, swipes, images), otherwise they follow rules. Components that are switched
   off in the experiment (memory, stress and reward) are not shown. Rarely needed settings sit in *Advanced parameters* panels, closed by default; choosing a recommender shows what it does in the side column.
   The agents' daily rhythm comes from the activity profiles of the population, so the client page does not repeat it.
   The client page (*Client details*) shows the state, extends the simulation (days are added to the total; start the
   client again and it runs what is left) and edits the settings while the client is stopped. Profile images are
   generated in the background by default: the simulation starts at once and each photo appears as soon as it is
   ready (a vision-based swipe model waits for them instead). Before it starts, YSocial rebuilds the input file from
   the database and validates the folder with the offline validator of the runtime; a run that would fail to start is
   refused with the reason.
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
- **How a match went**: the matches table and the chat show the outcome of each match with coloured chips (date went well, so-so or badly - the agents decided not to continue off the platform - date declined or unanswered, ghosting when the last message stays unanswered for `ghosting_threshold_slots` (default 48), no opener, unmatched, blocked, left the platform, left together). Dates and their answers are also written in the chat by the agents. Researchers and admins find the same counts as lifecycle statistics on each agent's profile; an account's own view only says that a match ended. Time travel hides outcomes that had not happened at the chosen round; the answer to a proposal has no timestamp of its own, so it is placed at the proposal's round.
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

Always available: people can play on the same platform as the agents in every dating experiment (`human.enabled` is
set by YSocial). The experiment settings (section *Human participation*) hold the maximum participants, the minimum
round time, the request limits and which interactions people may use. Leave *Participant mode* on in the frontend settings, and assign the users to the
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

## Names, photos and the profile page

A generated dating population gives its agents names of real-looking people that follow the nationality and the
gender (the same locales as the other platforms), not `user_N`; a population uploaded from a file keeps the names
of the file. With `profile_generation.images.use_caption` (on by default) each image shows the agent (age, gender,
nationality and looks) inside the scene its photo caption describes. The profile page of the frontend shows the
profile with a hero, cards that fade in, a photo gallery with a lightbox and, for researchers, bars for the latent
variables.
