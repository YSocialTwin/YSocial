# Instant messaging analytics: how the derived database is filled

The YSocial analytics pages (toxicity, sentiment, opinion, stress/reward, topic, hashtag, network, emotion; the
recommender page stays unavailable) run on an instant messaging experiment through a **derived analytics database**,
`analytics_im.db`, in the experiment folder. It is owned by YWeb, has the shape of a YSocial experiment database
(its tables are created from YSocial's own models) and is rebuilt from the run database of YInstantMessaging, which
is only ever opened read-only. IM never reads it; YWeb never writes the run database.

## When it is built

- when an analytics page of the experiment is opened, and when the experiment details page is opened, if the run
  database changed since the last build (a comparison of the file and its non-empty write-ahead log);
- by **Refresh analytics data** on the details page (`POST /admin/im/analytics/<id>/refresh`), which forces a rebuild.

The build is a full rebuild into a temporary file followed by an atomic replace; `etl_state` records the watermark
(source signature, last round, day and slot, schema versions). Running it twice gives identical rows. If it fails,
the message is shown on the details page and the previous derived file stays. A single build runs at a time per
experiment. On a 7-day database with 100 agents and 20,000 messages it takes well under a second and about 90 MB.

The file is a run artifact: it is left out of clones and downloads and removed by a reset.

## Mapping

| Derived table | Built from (IM) | Present when |
| --- | --- | --- |
| `rounds` | `rounds`; `hour` is the slot, copied as is (slots count from 1) | always |
| `user_mgmt` | `accounts`; persona gives leaning, age, profession, gender, nationality, education, Big Five; `is_page` for page accounts; `user_type` is `human` for human accounts | always |
| `post` | `messages` in round order; a reply has `comment_to` = the parent post, a forward has `shared_from` = the origin post, `thread_id` follows the thread root; deleted messages are kept | always |
| `reactions` | `reactions`; the negative emoji of IM's stress/reward table (and a few others) are `dislike`, all others `like` | rows exist |
| `mentions` | `mentions` | rows exist |
| `interests`, `post_topics` | `topics`, `message_topics` (topics that are used) | rows exist |
| `hashtags`, `post_hashtags` | `hashtags`, `message_hashtags` | rows exist |
| `post_toxicity` | `annotations` of the `toxicity_*` methods with status `ok` (the first method by name when several ran) | rows exist |
| `post_sentiment` | `annotations` of the `sentiment_*` methods with status `ok`; topic = the first topic of the message | rows exist |
| `emotions`, `post_emotions` | `annotations` of the `emotion*` methods with status `ok` (`{"emotions": [...]}`, one row per label; the first method by name when several ran) | rows exist |
| `agent_opinion` | `agent_opinions` (`tid` is the round) | rows exist |
| `stress_reward` | `stress_reward` (same columns) | rows exist |
| `follow` | `chat_members` joined with `chats.owner_account_id`: a member follows the owner of the chat (`follow` at the first join, `unfollow` at the last leave when every membership with that owner ended); the owner's own row is skipped | rows exist |

No table is created for recommendations: IM has none, so that page keeps its normal unavailable state. Chat membership is the only relation IM has that looks like a follow, which is why the network page can show it. The details page offers a card for a page only when its tables exist, and
`Exps.annotations` is extended with `opinions`, `sentiment`, `emotion` and `toxicity` when the derived database holds them, so
the existing checks of the opinion page pass without a special rule.

## What is not claimed

A slot is not an hour, a chat message is not a feed post and IM has no recommender system, so the figures are not
directly comparable with runs of other platforms. Every page of an IM experiment says so in a note. Which
interactions should define a network edge is still open: the network page uses the tables it finds (replies and
forwards through `post`, `reactions`, `mentions`); chat membership is not an edge.
