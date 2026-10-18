"""Photo caption prompts must not mention the simulation day/slot: models copy it into the caption."""
import json
import pathlib

import pytest

pytestmark = pytest.mark.unit

ROOT = pathlib.Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("lang", ["en", "it"])
def test_pack_caption_prompt_has_no_day_or_slot(lang):
    data = json.loads((ROOT / "data_schema" / "prompts" / lang / "prompts_ygram.json").read_text(encoding="utf-8"))
    text = json.dumps(data["generate_caption"], ensure_ascii=False)
    assert "{day}" not in text and "{slot}" not in text


@pytest.mark.integration
@pytest.mark.external_repo
@pytest.mark.parametrize("name", ["prompts_internal.json", "prompts_internal.it.json"])
def test_internal_caption_prompts_have_no_day_or_slot(name):
    path = ROOT / "external" / "YPhotoSharing" / "YPhotoSharing" / name
    if not path.exists():
        pytest.skip("external repo not present")
    data = json.loads(path.read_text(encoding="utf-8"))
    for key in ("remote_batch_service__generate_caption__1", "remote_batch_service__batch_generate_captions__1"):
        assert "{day}" not in data[key] and "{slot}" not in data[key]
        assert "{v2}" not in data[key] and "{v3}" not in data[key]


@pytest.mark.integration
@pytest.mark.external_repo
@pytest.mark.parametrize("name", ["prompts_internal.json", "prompts_internal.it.json"])
def test_microblogging_tweet_prompt_has_no_day_or_slot(name):
    path = ROOT / "external" / "YSimulator" / "YSimulator" / name
    if not path.exists():
        pytest.skip("external repo not present")
    text = json.loads(path.read_text(encoding="utf-8"))["llm_service__init____2"]
    assert "{day}" not in text and "{slot}" not in text
