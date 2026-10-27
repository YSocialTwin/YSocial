# Instant messaging experiments

YSocial can run a third platform next to microblogging, forum and photo sharing: **instant messaging** (channels,
groups, private chats, forwards, reactions, replies, forum topics inside chats). The simulation is done by the
[YInstantMessaging](https://github.com/YSocialTwin/YInstantMessaging) runtime (IM), a plugin installed from the
**Plugins** page. YSocial creates the experiment, launches the IM server and its clients, monitors them and shows the
result; the simulation itself and its database belong to IM.

## Create and run an experiment

1. Install the *Instant Messaging* runtime from **Plugins**. The platform appears in the experiment form only once it
   is installed.
2. Create the experiment and choose *Instant Messaging*. As on the other platforms, the form asks nothing specific to
   the platform. On the experiment details page, *Experiment Configuration* has the same switches as the other
   experiments (annotations, opinion dynamics, stress and reward, memory); the experiment starts locked until
   *Update Configuration* confirms them. The server-level settings that only matter to people taking part (minimum
   round seconds, maximum number of participants) are in its *Advanced Settings*; they cannot change once a run has
   started.
3. Create a population (type *instant messaging*: agents and pages) and a client. The client form has the sections of
   the other platforms: the run (length in days, start date, ticks per round, seed), the language model (the URL of
   an OpenAI-compatible service, *Fetch Models*, model, temperature, maximum tokens), agent memory (only when it is
   on in the experiment), the relevance of each agent action, topic interests, optional hourly activity, and
   an optional *Chats by Topic* editor (channels and groups that exist at the start, with their topics; they are
   written to the client's own topic catalog), and *Advanced Settings* as a structured form (scheduling, topology, topics, attention, reactive replies, discovery,
   moderation, archetypes, churn, language-model reliability, logs, and more) with the defaults of IM. The length, the
   start date and the round length are carried into the experiment's server configuration: the first client sets the
   start date and the round length, later clients must agree, and nothing but a longer run can change once the
   server has started. When opinion dynamics are on in the experiment, each client has a link to its own
   *Opinion Configuration* page (distributions per topic, bounded confidence or LLM evaluation).
   The client form validates the files with `yim-validate` before anything is written; a file that IM would refuse
   is refused here with the same messages.
4. Start the server, then the client. Pause, resume, stop, reset, clone, download and upload work as for the other
   platforms. A run that stopped can be resumed; a change of a hashed input between runs stops the client with the
   message "configuration changed since the run started" and *Reset* restores the ability to run.

The IM database is written only by the IM server. YSocial never writes it: pages read it read-only, and the YSocial
tables are never created in it.

## What researchers see

- **Observer pages** (chat list, history, threads, forum topics, members, search, profiles, time travel). Three
  viewpoints: the public observer, one agent's account, and the researcher overview (with deleted messages as
  tombstones). A differential test checks that what a viewpoint sees equals what IM's own visibility rules allow.
- **Analytics**: toxicity, sentiment, opinion dynamics, stress/reward, topics, hashtags and the network page work on
  a derived database, `analytics_im.db`, rebuilt from the run database; see [the mapping](im-analytics-mapping.md).
  Emotion and recommender pages stay unavailable. Messages count as posts, replies as comments, forwards as shares,
  and slots count from 1.
- **Export and reports** on the experiment details page (`yim-export`, snapshot while running).

## Frontend settings

*Frontend settings* has an instant messaging section: times, badges, forwarded origin, reactions, member roles, the
opening view, page size or infinite scroll, time travel for viewers, public observer pages, polling interval, the
interaction switches (post, comment, share, like, notifications) and the participant notice.

## Human participation

People can register at any time, as on the other platforms: there is nothing to decide when the experiment is
created. Those who join the experiment take part as **participants**: they read their own chats and can post, reply, forward, react, edit and
delete (the last two only if the run enables edits), join and leave chats, invite, search and read notifications.
They cannot create chats: in IM that is an agent mechanism with quotas.

How it works, and what to keep in mind:

- Each participant has a deterministic account in the run (kind *human*, origin *human*); entering twice never
  creates two. The name shown is a pseudonym (`participant-<id>`).
- Writes go through a **gateway**, a local service started with the run (after the server, before the clients) and
  stopped first. It listens on loopback only, requires a per-run token, never lets a request choose the account (it
  comes from the session), accepts only the actions above, limits their rate and de-duplicates retries. The browser
  sends its own CSRF token.
- The interaction switches of the frontend settings are enforced by the server (403), not only hidden.
- What a participant reads is recorded as exposures, like the agents' feed: the pages read the database, and each
  view tells the gateway which messages were shown (one request per participant, round and chat, so refreshing does
  not count twice; the server applies the same visibility checks as for `read_chat`).
- Humans never hold up the simulation: the gateway is a non-blocking client, so an absent or slow person cannot stall
  a round. *Minimum round seconds* (default 0, a lower bound only) gives people a window to act in a slow-paced run;
  the right value depends on the people involved, so try it with someone at the keyboard.
- If the gateway stops, the run goes on and the participant page shows "connection lost"; an action sent twice is
  applied once.
- **A run with humans is not reproducible**: it cannot be repeated from the same files. The experiment details page
  says so.
- Notifications from other clients' current round appear one round later (IM design).
- Participants entering when the gateway is down see the public view.

The researcher can write a short notice, shown once before the first entry (frontend setting *participant notice*,
up to 4000 characters).

## Limits

- Local SQLite only; remote or PostgreSQL IM experiments are refused.
- Importing an IM zip creates the experiment and its inputs; clients are created again from the form.
