import json
from pathlib import Path


def test_hpc_prompt_json_includes_output_contracts():
    prompts_path = Path("data_schema/prompts_hpc.json")
    data = json.loads(prompts_path.read_text())

    comment_prompt = data["generate_comment"]["user_template"]
    share_prompt = data["generate_share_commentary"]["user_template"]
    news_prompt = data["generate_news_commentary"]["user_template"]

    assert "Output ONLY the comment text." in comment_prompt
    assert (
        "Do not explain, summarize, quote the prompt, add preambles, or wrap it in markdown."
        in comment_prompt
    )

    assert "Output ONLY the commentary text." in share_prompt
    assert (
        "Do not explain, summarize, quote the prompt, add preambles, or wrap it in markdown."
        in share_prompt
    )

    assert "Output ONLY the tweet text." in news_prompt
    assert (
        "Do not explain, summarize, quote the prompt, add preambles, or wrap it in markdown."
        in news_prompt
    )
