import json
from pathlib import Path
from string import Formatter


def _get_placeholder_names(template: str) -> list[str]:
    return [
        field_name for _, field_name, _, _ in Formatter().parse(template) if field_name
    ]


def test_hpc_prompt_json_includes_output_contracts():
    prompts_path = Path("data_schema/prompts_hpc.json")
    data = json.loads(prompts_path.read_text())

    comment_prompt = data["generate_comment"]["user_template"]
    share_prompt = data["generate_share_commentary"]["user_template"]
    news_prompt = data["generate_news_commentary"]["user_template"]
    search_prompt = data["generate_search_action"]["user_template"]

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

    assert "Reply with ONLY ONE WORD" in search_prompt
    assert "COMMENT, SHARE, LIKE, LOVE, LAUGH, ANGRY, SAD, or IGNORE" in search_prompt

    assert "Output ONLY the tweet text." in news_prompt
    assert (
        "Do not explain, summarize, quote the prompt, add preambles, or wrap it in markdown."
        in news_prompt
    )


def test_hpc_comment_prompt_placeholders_are_well_formed():
    prompts_path = Path("data_schema/prompts_hpc.json")
    data = json.loads(prompts_path.read_text())

    comment_prompt = data["generate_comment"]["user_template"]
    placeholders = _get_placeholder_names(comment_prompt)

    assert "thread_context_instruction" in placeholders
    assert "author_name" in placeholders
    assert "post_content" in placeholders
    assert all(name == name.strip() for name in placeholders)
    assert all("\n" not in name and "\r" not in name for name in placeholders)
