# Prompt glossary (English → Italian)

Used for the Italian prompt packs (`data_schema/prompts/it/` and every `prompts_internal.it.json`). Anything not
listed here follows ordinary Italian usage. The glossary is part of the review: the native-speaker reviewer signs
off on it together with the translations.

## Register and voice

- The prompts speak to the model in the **second person singular** (*tu*): "Sei un utente dei social media",
  "Scrivi un breve post". No *Lei*, no *voi*.
- Instructions use the **imperative** ("Leggi", "Scrivi", "Non descrivere"); persona sentences use the present.
- Tone requests stay tone requests: "informal tone" → "tono informale".
- Texts the agent must write are asked **in the agent's language** (the `{self.language}` field, translated through
  `profile_values.json`).
- Keep the structure of the English text: same paragraphs, same `##MARKER##` lines, same bullet layout. Only the
  words change. Never "improve" a prompt while translating it.

## Never translated (protocol tokens and structure)

| Kind | Examples |
| --- | --- |
| Answer tokens the code reads | `YES`, `NO`, `NEUTRAL`, `LEFT`, `RIGHT`, `NONE`, `AGREE`, `DISAGREE`, `LIKE`, `DISLIKE`, `LOVE`, `LAUGH`, `ANGRY`, `SAD`, `IGNORE` |
| Action names | `POST`, `COMMENT`, `READ`, `SEARCH`, `FOLLOW`, `SHARE`, `IMAGE`, `CAST`, `REPORT`, `SHARE_LINK`, `SHARE_IMAGE`, `REPORT_TOXIC`, `REPORT_OFFENSIVE` |
| Emotion labels (GoEmotions) | `admiration`, `amusement`, `anger`, … (the list handed to the model and parsed back) |
| JSON keys and enum values inside prompts | `relation_label`, `summary_text`, `agree`, `hostile`, … |
| Markers | `##BEGIN INPUT##`, `##TEXT START##`, `#T:` |
| Fields | `{self.name}`, `{topic}`, … (identical, validated by `validate_pack.py`) |

When a prompt asks the model to answer with one of the tokens, the Italian text says so explicitly and writes the
token in capitals: "scrivi YES se ti piace, NO altrimenti, NEUTRAL negli altri casi".

## Terms

| English | Italian | Note |
| --- | --- | --- |
| post (noun) | post | not "messaggio" |
| tweet | tweet | kept: the platform wording of the English prompts |
| comment | commento | |
| thread / conversation thread | thread / conversazione | "thread" for a Reddit-style thread |
| reply | risposta | |
| share / reshare | condividere / ricondividere | |
| follow / unfollow | seguire / smettere di seguire | `{action}` goes through `profile_values.json` |
| reaction | reazione | |
| agent | agente | |
| persona / profile | profilo | "persona" only for "role play as" |
| role-play | interpretare / recitare la parte di | |
| Handler | Handler | internal role name, kept |
| Social Media Manager | Social Media Manager | kept |
| stance | posizione | |
| topic | argomento | |
| summary | riassunto | |
| article | articolo | |
| toxicity (level) | (livello di) tossicità | values: nullo, basso, medio, alto |
| confrontational | conflittuale | |
| political leaning | orientamento politico | |
| informal / formal tone | tono informale / formale | |
| stress | stress | |
| reward | ricompensa | |
| memory | memoria | |
| evidence | evidenze | |
| moderator | moderatore | |

## Profile values

`profile_values.json` maps the English values stored in the database (profession, nationality, language, gender,
leaning, education level, toxicity, Big Five phrases, follow/unfollow) to Italian. Choices that keep the sentences
grammatical whatever the agent's gender:

- nationality is an adjective agreeing with the feminine noun *nazionalità* ("di nazionalità italiana");
- professions are given in the masculine/neutral form ("di professione infermiere");
- the Big Five traits are listed after a neutral lead-in ("Tratti di personalità: …"), not after "Sei".
