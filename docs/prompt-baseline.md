# English baseline (gate G0)

Status: **not measured yet.** No LLM server was reachable from the environment that prepared the scripts, so the live numbers below are empty. Run the script on the two models chosen for the pilot and paste the results here.

## How to run

```
python scripts/prompts/baseline_parse.py --endpoint <OpenAI-compatible base URL> --model <model name> \
    --n 50 --seed 1 --out docs/baseline_<model>.json
```

Each round asks four questions with the current English prompts of `data_schema/prompts.json` (action choice, follow decision, reaction, vote) and applies the same token tests as `YClient/y_client/classes/base_agent.py`. `--simulate` checks the script without a network.

## Results

| Model | Parsing success | Action | Follow | Reaction | Vote | Mean prompt tokens | Mean completion tokens |
| --- | --- | --- | --- | --- | --- | --- | --- |
| (model 1) | | | | | | | |
| (model 2) | | | | | | | |

Gate G0 asks for at least 95% parsing success on both models. If the English baseline is lower, the English prompts or parsers are fixed first.

## What the client parsers do today (read from the code, not measured)

- The answer is uppercased where needed, `!` is removed and the text is split on whitespace; a token matches only as a whole word. `NEUTRAL.` or `YES,` therefore does **not** match, while `NEUTRAL` and `yes` (where the code uppercases) do. Step 2 makes the parser tolerant of punctuation and case; the baseline measures today's behaviour first.
- The action choice scans for the tokens in a fixed order (`COMMENT`, `POST`, `READ`, `SEARCH`, `FOLLOW`, `SHARE`, `CAST`, `IMAGE`); an answer containing two of them takes the first in that order.
- Reaction and follow prompts also use `YES`, `NO`, `NEUTRAL`; the vote prompt uses `LEFT`, `RIGHT`, `NONE`.
