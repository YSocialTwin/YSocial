"""Appearance and profile pictures of the agents of a population (any platform).

The *Appearance* section of the population form describes how the agents look. It is optional and independent of
the platform: the traits are stored as ``appearance.*`` custom features of the standard agents. A population that
carries the Dating fields keeps its traits in ``dating.appearance.*``; both are read the same way.

With the (default-off) picture toggle the agents also get a profile picture drawn by a text-to-image model (the same
settings as the YDating client: style, generator, model, denoising steps). The pictures are written in the media
folder (``<home>/media/agents``), linked to the agent through ``Agent.profile_pic`` and served at ``/media/agents/``.
The generation runs in a background thread and reports its progress in the notifications menu. A picture is deleted
together with its agent (see :func:`delete_picture_file`, called by the ORM listener of ``Agent``).
"""

from __future__ import annotations

import hashlib
import importlib.util
import os
import random
import re
import struct
import threading
import zlib
from typing import Any, Dict, Iterable, List, Optional

MEDIA_URL_PREFIX = "/media/agents/"
FEATURE_PREFIXES = ("appearance.", "dating.appearance.")
STYLES = ("photorealistic", "cartoon")
GENERATORS = ("diffusion", "stub")
DEFAULT_MODEL = "segmind/tiny-sd"
DEFAULT_STEPS = 20
NOTIFICATION_TITLE = "Agent profile pictures"
PROGRESS_RE = re.compile(r"\s*\[progress:(\d+)/(\d+)\]")
_PROGRESS_EVERY = 1  # a picture takes seconds with a model: report every one


# ------------------------------------------------------------------ media folder


def media_dir() -> str:
    from y_web.src.system.path_utils import get_writable_path

    return get_writable_path(os.path.join("media", "agents"))


def picture_url(agent_id: int) -> str:
    return f"{MEDIA_URL_PREFIX}{int(agent_id)}.png"


def is_media_url(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(MEDIA_URL_PREFIX)


def picture_file(url: str) -> Optional[str]:
    """Absolute path of the file a media url names (None for anything that is not a plain file of the folder)."""
    if not is_media_url(url):
        return None
    name = url[len(MEDIA_URL_PREFIX) :]
    if not name or name != os.path.basename(name) or name.startswith("."):
        return None
    return os.path.join(media_dir(), name)


def delete_picture_file(url: Any) -> bool:
    """Delete the picture an agent points to; ``False`` when there is nothing to delete."""
    path = picture_file(url) if isinstance(url, str) else None
    if not path:
        return False
    try:
        os.remove(path)
        return True
    except OSError:
        return False


def delete_pictures_of(agent_ids: Iterable[int]) -> int:
    """Delete the pictures of agents that are removed with a bulk statement (the ORM listener does not see those)."""
    from sqlalchemy import select

    from y_web import db
    from y_web.src.models import Agent

    ids = [int(i) for i in agent_ids]
    removed = 0
    for start in range(0, len(ids), 500):
        rows = db.session.execute(
            select(Agent.profile_pic).where(Agent.id.in_(ids[start : start + 500]))
        ).all()
        removed += sum(delete_picture_file(r[0]) for r in rows)
    return removed


# ------------------------------------------------------------------ appearance


def available() -> bool:
    """The optional packages of the image model (``torch`` and ``diffusers``) can be imported."""
    return all(importlib.util.find_spec(m) is not None for m in ("torch", "diffusers"))


def defaults() -> Dict[str, Any]:
    """Values proposed by the form (the weights of the generator of the Dating platform)."""
    from y_web.src.dating import population as dp

    return {
        "appearance": dp.APPEARANCE_DEFAULTS,
        "appearance_options": dp.APPEARANCE_OPTIONS,
        "height": dp.HEIGHT_DEFAULT_RANGE,
        "glasses": dp.GLASSES_DEFAULT_PERCENT,
        "styles": STYLES,
        "model": DEFAULT_MODEL,
        "steps": DEFAULT_STEPS,
    }


def appearance_config_from_form(form) -> Dict[str, Any]:
    """``{trait: {label: percent}}`` plus ``height_cm`` ``[min, max]`` and ``glasses`` (0-1) of the form."""
    from y_web.src.dating import population as dp

    cfg: Dict[str, Any] = {}
    for key in dp.APPEARANCE_LABELS:
        weights = dp._percentages(form, f"d_appearance_{key}")
        if weights:
            cfg[key] = weights
    height = dp._pair(form, "appearance_height_cm", int, 100, 250)
    if height:
        cfg["height_cm"] = list(height)
    glasses = dp._number(
        form.get("appearance_glasses"), "appearance_glasses", float, 0, 100
    )
    if glasses is not None:
        cfg["glasses"] = glasses / 100.0
    return cfg


def pictures_config_from_form(form) -> Dict[str, Any]:
    """Settings of the picture generation (the fields of the YDating client)."""
    style = (form.get("pictures_style") or "photorealistic").strip()
    generator = (form.get("pictures_generator") or "diffusion").strip()
    if style not in STYLES:
        raise ValueError(f"unknown image style: {style}")
    if generator not in GENERATORS:
        raise ValueError(f"unknown image generator: {generator}")
    try:
        steps = int(form.get("pictures_steps") or DEFAULT_STEPS)
    except ValueError:
        raise ValueError("pictures_steps: must be an integer") from None
    if not 1 <= steps <= 100:
        raise ValueError("pictures_steps: must be between 1 and 100")
    return {
        "style": style,
        "generator": generator,
        "model": (form.get("pictures_model") or DEFAULT_MODEL).strip() or DEFAULT_MODEL,
        "inference_steps": steps,
    }


def _pick(rng: random.Random, weights: Dict[str, float]) -> str:
    labels = list(weights)
    return rng.choices(labels, weights=[weights[k] for k in labels])[0]


def sample(cfg: Dict[str, Any], rng: random.Random) -> Dict[str, str]:
    """The traits of one agent: a label per trait drawn from its weights, a height and glasses."""
    from y_web.src.dating import population as dp

    traits: Dict[str, str] = {}
    for key in dp.APPEARANCE_LABELS:
        weights = cfg.get(key)
        if weights:
            traits[key] = _pick(rng, weights)
    height = cfg.get("height_cm")
    if height:
        traits["height_cm"] = str(rng.randint(int(height[0]), int(height[1])))
    if cfg.get("glasses") is not None:
        traits["glasses"] = "true" if rng.random() < float(cfg["glasses"]) else "false"
    return traits


def assign_appearance(
    agent_ids: Iterable[int], cfg: Dict[str, Any], seed: Optional[int] = None
) -> int:
    """Draw and store the appearance of the agents that have none; returns the agents that got one."""
    from sqlalchemy import insert

    from y_web import db
    from y_web.src.models import Agent_Custom_Feature

    ids = sorted(int(i) for i in agent_ids)
    have = set(read_appearance(ids))
    rng = random.Random(seed if seed not in (None, "") else None)
    rows, done = [], 0
    for agent_id in ids:
        if agent_id in have:
            continue
        traits = sample(cfg, rng)
        if not traits:
            continue
        done += 1
        rows += [
            {
                "agent_id": agent_id,
                "feature_type": "custom",
                "key": f"appearance.{k}",
                "value": v,
            }
            for k, v in traits.items()
        ]
    if rows:
        db.session.execute(insert(Agent_Custom_Feature), rows)
        db.session.commit()
    return done


def read_appearance(agent_ids: Iterable[int]) -> Dict[int, Dict[str, str]]:
    """``{agent id: {trait: value}}``; ``appearance.*`` wins over ``dating.appearance.*``."""
    from sqlalchemy import or_, select

    from y_web import db
    from y_web.src.models import Agent_Custom_Feature

    ids = [int(i) for i in agent_ids]
    out: Dict[int, Dict[str, str]] = {}
    for start in range(0, len(ids), 500):
        chunk = ids[start : start + 500]
        rows = db.session.execute(
            select(
                Agent_Custom_Feature.agent_id,
                Agent_Custom_Feature.key,
                Agent_Custom_Feature.value,
            ).where(
                Agent_Custom_Feature.agent_id.in_(chunk),
                or_(*[Agent_Custom_Feature.key.like(p + "%") for p in FEATURE_PREFIXES]),
            )
        ).all()
        for agent_id, key, value in sorted(rows, key=lambda r: r[1].startswith("dating.")):
            traits = out.setdefault(agent_id, {})
            name = key.split("appearance.", 1)[1]
            traits.setdefault(name, value)
    return out


# ------------------------------------------------------------------ prompt


_FIELDS = (
    ("age", "{} years old"),
    ("gender", "{}"),
    ("hair_length", "{} hair"),
    ("hair_color", "{}"),
    ("hair_style", "{}"),
    ("eye_color", "{} eyes"),
    ("skin_tone", "{} skin"),
    ("build", "{} build"),
    ("facial_hair", "{}"),
    ("distinctive_features", "{}"),
    ("mood", "{} expression"),
    ("photo_style", "{}"),
)
_OPENING = {
    "photorealistic": "profile picture of a real person, realistic human face",
    "cartoon": "cartoon illustration of a fictional character, profile picture",
}
_CLOSING = {
    "photorealistic": ["photorealistic, natural light, sharp focus"],
    "cartoon": ["stylised cartoon drawing, not a photograph"],
}


def compose_prompt(
    age: Any, gender: Any, traits: Dict[str, Any], style: str = "photorealistic"
) -> str:
    """English text-to-image prompt from the visible traits only (same wording as the YDating client)."""
    if style not in STYLES:
        raise ValueError(f"unknown image style: {style}")
    values = dict(traits or {})
    values["age"], values["gender"] = age, gender
    parts = [_OPENING[style]]
    for key, fmt in _FIELDS:
        if key == "photo_style" and style == "cartoon":
            continue
        v = values.get(key)
        if v not in (None, "", 0):
            parts.append(fmt.format(v))
    if str(values.get("glasses")).lower() == "true":
        parts.append("wearing glasses")
    parts.extend(_CLOSING[style])
    return ", ".join(parts)


# ------------------------------------------------------------------ generators


def _png(width: int, height: int, rgb) -> bytes:
    def chunk(tag, data):
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    raw = zlib.compress((b"\x00" + bytes(rgb) * width) * height)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", raw)
        + chunk(b"IEND", b"")
    )


class StubGenerator:
    """Deterministic flat-colour PNG: for tests and dry runs (no model, no extra packages)."""

    model = "stub"

    def generate(self, prompt: str, seed: int = 0) -> bytes:
        return _png(64, 64, hashlib.sha256(f"{seed}|{prompt}".encode()).digest()[:3])


# distilled models: the steps and guidance they were trained for
_PRESETS = {"stabilityai/sd-turbo": {"max_steps": 4, "guidance_scale": 0.0}}


class DiffusionGenerator:  # pragma: no cover - needs a model
    """Local ``diffusers`` text-to-image pipeline, loaded on first use."""

    def __init__(self, model: str = DEFAULT_MODEL, steps: int = DEFAULT_STEPS):
        self.model, self.steps, self._pipe = model, steps, None

    def _load(self):
        try:
            import torch
            from diffusers import AutoPipelineForText2Image
        except ImportError as exc:
            raise RuntimeError(
                "image generation needs the optional packages: pip install torch diffusers"
            ) from exc
        device = (
            "cuda"
            if torch.cuda.is_available()
            else (
                "mps"
                if getattr(torch.backends, "mps", None)
                and torch.backends.mps.is_available()
                else "cpu"
            )
        )
        dtype = torch.float16 if device == "cuda" else torch.float32
        self._pipe = AutoPipelineForText2Image.from_pretrained(
            self.model, torch_dtype=dtype
        ).to(device)
        self._pipe.set_progress_bar_config(disable=True)

    def generate(self, prompt: str, seed: int = 0) -> bytes:
        import io

        import torch

        if self._pipe is None:
            self._load()
        preset = _PRESETS.get(self.model) or {}
        options: Dict[str, Any] = {
            "num_inference_steps": min(self.steps, preset.get("max_steps", self.steps))
        }
        if "guidance_scale" in preset:
            options["guidance_scale"] = preset["guidance_scale"]
        gen = torch.Generator("cpu").manual_seed(seed)
        image = self._pipe(prompt, generator=gen, **options).images[0]
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return buf.getvalue()


def make_generator(cfg: Dict[str, Any]):
    kind = cfg.get("generator", "stub")
    if kind == "stub":
        return StubGenerator()
    if kind == "diffusion":
        return DiffusionGenerator(
            cfg.get("model") or DEFAULT_MODEL, int(cfg.get("inference_steps") or DEFAULT_STEPS)
        )
    raise ValueError(f"unknown image generator: {kind}")


# ------------------------------------------------------------------ background job


def _set_notification(notification_id: int, **fields) -> Optional[str]:
    """Update the notification; returns its status (``None`` when it no longer exists)."""
    from y_web import db
    from y_web.src.models import DownloadNotification

    row = db.session.get(DownloadNotification, notification_id)
    if row is None:
        return None
    for key, value in fields.items():
        setattr(row, key, value)
    db.session.commit()
    return row.status


def progress_message(done: int, total: int) -> str:
    return f"Generating profile pictures: {done} of {total} [progress:{done}/{total}]"


def start_generation(app, user_id: int, agent_ids: List[int], cfg: Dict[str, Any]):
    """Create the notification and run :func:`run_generation` in a daemon thread; returns ``(notification id, thread)``."""
    from y_web import db
    from y_web.src.models import DownloadNotification

    ids = [int(i) for i in agent_ids]
    notification = DownloadNotification(
        user_id=user_id,
        title=NOTIFICATION_TITLE,
        message=progress_message(0, len(ids)),
        status="processing",
        is_read=False,
    )
    db.session.add(notification)
    db.session.commit()
    nid = notification.id
    thread = threading.Thread(
        target=run_generation,
        args=(app, nid, ids, cfg),
        name=f"profile-pictures-{nid}",
        daemon=True,
    )
    thread.start()
    return nid, thread


def run_generation(app, notification_id: int, agent_ids: List[int], cfg: Dict[str, Any]) -> int:
    """Draw one picture per agent, write it in the media folder and link it; reports progress to the notification.

    The job stops when the notification is cancelled; an agent deleted meanwhile is skipped.
    Returns the pictures made.
    """
    from y_web import db
    from y_web.src.models import Agent

    made = 0
    with app.app_context():
        try:
            generator = make_generator(cfg)
            style = cfg.get("style", "photorealistic")
            os.makedirs(media_dir(), exist_ok=True)
            traits = read_appearance(agent_ids)
            total = len(agent_ids)
            for n, agent_id in enumerate(agent_ids, start=1):
                agent = db.session.get(Agent, agent_id)
                if agent is not None:
                    prompt = compose_prompt(
                        agent.age, agent.gender, traits.get(agent_id, {}), style
                    )
                    seed = int(
                        hashlib.sha256(f"{agent_id}|{prompt}".encode()).hexdigest()[:8], 16
                    )
                    data = generator.generate(prompt, seed=seed)
                    db.session.expire_all()
                    if db.session.get(Agent, agent_id) is None:
                        continue  # deleted while the model was drawing
                    agent = db.session.get(Agent, agent_id)
                    path = os.path.join(media_dir(), f"{agent_id}.png")
                    with open(path, "wb") as handle:
                        handle.write(data)
                    agent.profile_pic = picture_url(agent_id)
                    db.session.commit()
                    made += 1
                if n % _PROGRESS_EVERY == 0 or n == total:
                    status = _set_notification(
                        notification_id, message=progress_message(n, total)
                    )
                    if status == "cancelled":
                        return made
            _set_notification(
                notification_id,
                status="ready",
                message=f"{made} profile pictures generated.",
                error_message=None,
            )
        except Exception as exc:  # the notification carries the reason
            db.session.rollback()
            _set_notification(
                notification_id,
                status="failed",
                message="Profile picture generation failed.",
                error_message=str(exc)[:500],
            )
    return made
