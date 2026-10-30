"""Photos of the people who play on the dating platform (IR-D-22, IR-D-30).

A person may add pictures to their profile, like the generated pictures of the agents. The file never
comes from a trusted source, so this module

* reads at most ``MAX_BYTES`` and refuses anything that is not a PNG, JPEG or WebP image (the type comes from
  the content, never from the name or the declared type),
* refuses images with too many pixels before decoding them,
* re-encodes the picture, which drops metadata (location, camera, authorship) and anything appended to the file,
* names the file after the account (``human/<account id>_<12 hex>.<ext>``), the only form the runtime accepts,
  and stores it under ``<experiment>/media/``, next to the pictures of the agents.

``resolve_media`` is the other side: it turns a name found in the database into a file inside that folder, or
into nothing. The web route serves only what it returns.
"""

import io
import os
import re
import secrets
from typing import Optional

MEDIA_DIR = "media"
HUMAN_DIR = "human"
MAX_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 40_000_000
MAX_SIDE = 1600
_FORMATS = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp"}
CONTENT_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
}
_NAME = re.compile(r"(?:human/)?[A-Za-z0-9_.-]{1,120}\.(png|jpg|jpeg|webp)")


class PhotoError(ValueError):
    """The upload is refused; ``code`` is one of ``empty``, ``too_large``, ``format``, ``pixels``, ``unreadable``
    and the web route turns it into a translated message."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def media_root(exp_folder: str) -> str:
    return os.path.join(exp_folder, MEDIA_DIR)


def store_upload(exp_folder: str, account_id: str, stream) -> str:
    """Validate, re-encode and store an uploaded picture; returns the ``media_url`` of the profile."""
    from PIL import Image, ImageOps, UnidentifiedImageError

    raw = stream.read(MAX_BYTES + 1)
    if not raw:
        raise PhotoError("empty")
    if len(raw) > MAX_BYTES:
        raise PhotoError("too_large")
    try:
        image = Image.open(io.BytesIO(raw))
        kind = _FORMATS.get(image.format or "")
        if kind is None:
            raise PhotoError("format")
        width, height = image.size
        if width * height > MAX_PIXELS:
            raise PhotoError("pixels")
        image.load()
    except PhotoError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise PhotoError("unreadable")
    image = ImageOps.exif_transpose(image)
    image.thumbnail((MAX_SIDE, MAX_SIDE))
    if kind == "jpg" and image.mode != "RGB":
        image = image.convert("RGB")
    elif image.mode not in ("RGB", "RGBA", "L"):
        image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
    out = io.BytesIO()
    if kind == "jpg":
        image.save(out, "JPEG", quality=85, optimize=True)
    elif kind == "webp":
        image.save(out, "WEBP", quality=85)
    else:
        image.save(out, "PNG", optimize=True)
    name = f"{HUMAN_DIR}/{account_id}_{secrets.token_hex(6)}.{kind}"
    path = os.path.join(media_root(exp_folder), name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.part"
    with open(tmp, "wb") as fh:
        fh.write(out.getvalue())
    os.replace(tmp, path)
    return name


def delete_upload(exp_folder: str, media_url: str) -> None:
    """Remove a file this module stored (after a refusal of the server); never raises."""
    path = resolve_media(exp_folder, media_url)
    if path and media_url.startswith(HUMAN_DIR + "/"):
        try:
            os.remove(path)
        except OSError:
            pass


def resolve_media(exp_folder: str, name: Optional[str]) -> Optional[str]:
    """The file of ``name`` inside the media folder of the experiment, or ``None``."""
    if not isinstance(name, str) or ".." in name or not _NAME.fullmatch(name):
        return None
    root = os.path.realpath(media_root(exp_folder))
    path = os.path.realpath(os.path.join(root, name))
    if os.path.commonpath([root, path]) != root or not os.path.isfile(path):
        return None
    return path


def content_type(name: str) -> str:
    return CONTENT_TYPES.get(
        name.rsplit(".", 1)[-1].lower(), "application/octet-stream"
    )
