# World Simulation: pilot with a real model (E9)

This protocol extends the short one in [World Simulation](world-simulation.md#pilot-protocol-before-a-large-run) to
sharing, topics, quoted content, pseudonyms and people. Run it once, on a small scale, before an expensive experiment
and before calling the multi-platform work a release candidate. Nothing in it needs the cloud: a local model is enough.

## What it checks

| Check | Question | Pass if |
|---|---|---|
| C1 Cross-post rate | Do agents cross-post as often as configured? | share of posts cross-posted within ±50% of `crosspost_propensity` |
| C2 Texts | Do cross-posted texts read as posts of the destination? | in a sample of 20, at least 18 have the right form and length and do not name the other platform |
| C3 Shares with attribution | Do shares of another agent's content arrive with their attribution? | every cross-posted share on a destination ends with the `↪ author @ platform: «excerpt»` line, and the block appears on the page |
| C4 Quote visibility | Is a quotation kept only when its author saw the content? | `quote_unseen` events exist only for agents with no exposure on that content; none for people |
| C5 Topics | Do topics travel and get created? | `topics_created` lists at least one topic per destination, and `topic_diffusion` shows it on more than one platform |
| C6 Pseudonyms | Are real names hidden when asked? | with `pseudonyms.enabled`, no author name of the origin platform appears on a destination |
| C7 People | Does a person's action cross-post once? | one enrolled person posts with "Also post on" ticked; the post appears once on each chosen platform |
| C8 Determinism | Does the same configuration give the same cross-post sequence? | two runs with the same seed and no people give the same cross-post counts per platform and tick |
| C9 Federation off | Is nothing changed when the federation is off? | the same experiments run outside a World Simulation behave as before (same table sizes, no `federation_*` tables read) |

## Setup

1. Three experiments with the same 10 agents: microblogging, forum and one more platform (instant messaging is a good
   choice because it has its own sharing action). Use the same local model for all, for example `qwen3:4b-instruct`
   served by Ollama. Three simulated days.
2. **News articles.** A share needs a post that contains a news article. Enable the news feeds in the microblogging and
   forum experiments and let them fill before the run, otherwise agents will almost never share and C3 cannot be
   judged. If you cannot provide articles, say so in the report: C3 then rests only on the unit tests.
3. Forum share: it opens only with `crosspost.mode = agent_action` (or `share.enabled: true` in the experiment
   configuration). Keep `agent_action` for this pilot.
4. World Simulation: `crosspost.mode = agent_action`, `crosspost_propensity` 0.3 (high enough for samples),
   exposures on (they switch on the quotation visibility check), topic migration on (default), pseudonyms off for the
   first run. Leave `discovery.quoted_weight` at 0.
5. For C7, enrol one person on at least two members before starting (World Simulation page, Configuration, Participants).
6. For C8, run twice with the same seed, no people, and compare.
7. For C6, rerun once with pseudonyms on.

## Run

Start the World Simulation, wait for the three days, stop it. Open **Analytics** and rebuild the derived database
before reading it.

## Read the results

- C1: the **Cross-posts** table divided by the posts of the origin platforms.
- C2 and C3: read 20 cross-posted texts on each destination page, and 10 shares.
- C3 and C4: **Shares** and **Share depth** tables; `quote_unseen` rows of the `federation_event` table in the coordinator database (`federation.db` in the World Simulation folder).
- C5: **Topics created**, **Topic first seen**, **Topic diffusion**.
- C7: **People** tables (`human_crossposts`, `human_activity`).
- C8: compare the CSV of the cross-posts of the two runs.

## Decision

Go if C1 to C5, C7 and C9 pass, and C6 and C8 pass when they apply. A failure of C1 or C2 sends you back to the prompts
`crosspost_adapt_<platform>` or to the propensity; a failure of C3 or C4 to the adapter of the platform that sent the
share; a failure of C9 is a regression and blocks the release candidate.

## Report

Write one paragraph per check with the numbers, the 20 sampled texts (as an appendix), the model and version, the seed,
the date and the commit of each repository. The progress document records the verdict as phase P6.
