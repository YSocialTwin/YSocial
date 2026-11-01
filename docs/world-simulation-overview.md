# World Simulation explained

*A plain-language introduction. The technical details are in the [researcher guide](world-simulation.md).*

## What a World Simulation is

A World Simulation lets the same community of simulated people live on several social platforms at once, so that what
happens on one platform can reach the others. Normally each platform (a microblog, a forum, a photo-sharing app, a
messaging app, a dating app) is its own separate world. A World Simulation connects them: the people are the same, the
platforms are different, and a small coordinator keeps everyone on the same clock and carries content between them.

Think of a town with a newspaper, a pub, a photo club and a dating night. The same residents go to all of them. Something
said at the pub may be repeated in the newspaper. A World Simulation reproduces that in a way researchers can measure.

It is off by default. Without a World Simulation, every platform behaves exactly as before.

## What you can study with it

- Does a story that spreads on the microblog also reach the forum, and how fast?
- Which people act as bridges between platforms?
- When a topic appears on one platform, does it spread to the others?
- What happens to a platform when its members spend their attention elsewhere?
- How do real people behave when they take part alongside simulated ones?

Every run keeps its own records, so the same question can be asked again with a different setting and compared.

## A day in the life of an agent

Take Maria, a simulated resident with accounts on the microblog, the forum and the messaging app.

1. **Same clock.** All platforms share one calendar. A tick is one time slot of one day, and platforms wait for each other.
2. **She posts.** On the microblog Maria writes about a local election and may also post it on the forum.
3. **The text adapts.** The forum prefers longer posts, so her text is rewritten for it, by the language model or by a
   simple fixed rule.
4. **The coordinator delivers it.** It checks the cross-post is allowed and hands it to the forum exactly once.
5. **Others react.** A forum user replies, and the topic "election" now exists on the forum if it did not before.
6. **Attention moves.** If Maria enjoys the forum more, she spends a little more time there.

## What agents can do across platforms

| Action | In plain words |
| --- | --- |
| Cross-post | Publish something on another platform where they also have an account, by a probability the researcher sets or by the agent's own choice. |
| Share with credit | Pass on someone else's content with a visible line saying who wrote it and where (`↪ author @ platform: «excerpt»`). |
| Carry a topic | A shared item brings its topic; if the destination lacks it, the topic is created there. |
| Share a match story | On dating, tell others how a match went (we keep seeing each other, ghosted, it did not work out). |
| Forward a message | On messaging, sharing means forwarding. |
| Move attention | The simulation shifts how much of an agent's day goes to each platform. |
| Discover a platform | Agents who see content cross-posted from a platform may join it. |
| Leave a platform | Agents leave a platform that holds almost none of their attention for several days. |

An agent can only credit someone whose content they have seen; otherwise the post goes out without the credit line.
Content is never sent back to the platform it came from.

## Texts and privacy

Each destination gets its own version of a post: the language model rewrites it, or a fixed rule shapes and trims it with
no model involved. Real people never go through a model, and can edit the text before it is sent.

When pseudonyms are on, other platforms see a label such as `participant-3f9a1c2b` instead of an author's name. The label
is stable within one simulation and differs in another. The stored data are unchanged.

## When real people take part

A person with a YSocial account can join next to the agents, with one identity and at most one account per platform.

1. **Enrol.** In the Configuration tab, under Participants, choose the user and the platforms. This also works while the
   simulation runs. On dating, the enrolment waits until the person has filled in a profile.
2. **Post as usual.** Under the text box, *Also post on* lists only the other platforms where you are enrolled.
3. **Edit per destination.** Each destination shows the text it will receive and you can change it.
4. **Stopped platforms.** If a platform is stopped, the post is kept and delivered after it restarts; a notice says so.

People are outside the rules that act on agents: attention, discovery, leaving and mood reports do not apply to them.

## What you see in the app

- **Create.** Choose two to five existing experiments, one per platform type, with the same population, simulated clock
  and hourly refresh; set a name, optional seed and options. The form checks the requirements.
- **Run.** The Execution tab starts, pauses, resumes and stops everything as one unit. Member experiments show a
  *World Simulation* badge. Several simulations can be queued from Schedule.
- **Analytics.** Attention, migration, cross-posts, cascades, share chains, bridge agents, topics and what each person did,
  with CSV download.
- **Keep and reuse.** Export to a zip, import elsewhere, copy (without people) or reset when stopped.

The interface is available in English and Italian.

## What is simulated, and what is not

- Agents are language-model characters; results describe the model's world, not proof of how real people act.
- Runs with real people are not repeatable; runs with only agents can be.
- No pilot has been run yet; its protocol is in [World Simulation pilot](world-simulation-pilot.md).
- Two experiments of the same platform type cannot be in one simulation; remote experiments and real-time clocks are not
  supported.

## Frequently asked questions

**Do I need a World Simulation to use YSocial?** No. It is optional and off by default.

**Does it change my existing platforms?** No, not unless they are part of a running World Simulation.

**Who decides what gets cross-posted?** A probability the researcher sets, or the agent's own choice, depending on the mode.

**Can content loop back to where it started?** No.

**Are real names shown on other platforms?** Only if pseudonyms are off.

**Can I join a running simulation?** Yes.

**What if a platform is stopped when I post?** Your post is kept and delivered when it restarts.

**Does the language model rewrite my posts?** No; only the fixed rule is used, and you can edit the result.

**Can I repeat a run exactly?** Yes if only agents take part.

**Where do I find the numbers?** In the Analytics tab, with a CSV download.

## Glossary

| Term | Meaning |
| --- | --- |
| World Simulation | Several platforms run together as one connected world (the *federation* in code). |
| Platform | One social app: microblog, forum, photo sharing, messaging or dating. |
| Member | A platform experiment taking part in a World Simulation. |
| Coordinator | The service that keeps the clock and carries content between members. |
| Tick | One time slot of one day on the shared clock. |
| Agent | A simulated person driven by a language model. |
| Identity | The single name an agent or person has across member platforms. |
| Cross-post | Publishing the same content on another platform. |
| Share with credit | Passing on content with a visible attribution line. |
| Topic migration | A topic travelling with shared content and created on the destination if missing. |
| Attention | How an agent's day is split across platforms. |
| Bridge agent | An agent whose posts reach more than one platform. |
| Pseudonym | A stable label replacing a real name. |
| Gateway | The door through which a real person acts on a platform. |
| Pilot | A small first run used to check the setup. |
