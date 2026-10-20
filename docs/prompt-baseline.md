# English baseline (gate G0)

Status: **one model measured; a second one was waived by the user for G0 (decision of 2026-10-17: one model only).** The scripts were prepared in an environment without access to an LLM server; the first run was made by the user on a local Ollama (details below). G0 therefore rests on a single, favourable model; the G3 comparison should add a second model if one becomes available.

## How to run

```
python scripts/prompts/baseline_parse.py --endpoint <OpenAI-compatible base URL> --model <model name> \
    --n 50 --seed 1 --out docs/baseline_<model>.json
```

Each round asks four questions with the current English prompts of `data_schema/prompts.json` (action choice, follow decision, reaction, vote) and applies the same token tests as `YClient/y_client/classes/base_agent.py`. `--simulate` checks the script without a network.

## Results

| Model | Parsing success | Action | Follow | Reaction | Vote | Mean prompt tokens | Mean completion tokens |
| --- | --- | --- | --- | --- | --- | --- | --- |
| llama3.2 (Ollama, local, 50 rounds, seed 1; `docs/baseline_llama3.2.json`) | 100% (200/200) | 100% | 100% | 100% | 100% | 98 to 114 | about 2 |

Gate G0 asks for at least 95% parsing success on both models. If the English baseline is lower, the English prompts or parsers are fixed first.

## What the client parsers do today (read from the code, not measured)

- The answer is uppercased where needed, `!` is removed and the text is split on whitespace; a token matches only as a whole word. `NEUTRAL.` or `YES,` therefore does **not** match, while `NEUTRAL` and `yes` (where the code uppercases) do. Step 2 makes the parser tolerant of punctuation and case; the baseline measures today's behaviour first.
- The action choice scans for the tokens in a fixed order (`COMMENT`, `POST`, `READ`, `SEARCH`, `FOLLOW`, `SHARE`, `CAST`, `IMAGE`); an answer containing two of them takes the first in that order.
- Reaction and follow prompts also use `YES`, `NO`, `NEUTRAL`; the vote prompt uses `LEFT`, `RIGHT`, `NONE`.

## Reading of the first result

All 200 answers of llama3.2 were accepted by the parsers (G0 threshold: at least 95%), with answers of about two tokens and 0.07 to 0.24 s per request. This model follows the one-word format very closely, so it is a favourable case: a result of 100% leaves no room to see a drop later, and the comparison of G3 will be more informative with a second, less obedient or larger model. These four prompts are also only a sample of the actions; comment and post generation, annotation and the Reddit memory prompts are not covered yet.
