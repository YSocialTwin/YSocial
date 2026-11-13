"""Forms generated from the JSON Schemas of YDating (plan S3, IR-D-06, IR-D-07, IR-D-10).

The runtime defines every configuration key once, in ``schemas/``, with a type, bounds, a default and a
description. YWeb does not keep a second list of settings: the advanced forms are generated from the schemas, and a
test checks that every leaf of a schema is either exposed or named as internal (with the reason). The module is
pure (no Flask, no database).
"""

import copy
import json
import math
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

SEPARATOR = "."
FIELD_PREFIX = "adv__"


class SettingsError(ValueError):
    """A submitted value is out of range or of the wrong type (``problems`` carry the reasons)."""

    def __init__(self, problems: Sequence[str]):
        self.problems = list(problems)
        super().__init__("; ".join(self.problems))


@dataclass
class Field:
    """One setting of a schema."""

    path: str
    kind: str  # bool, int, float, choice, text, numlist, json
    default: Any
    description: str
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    exclusive_minimum: Optional[float] = None
    choices: List[Any] = field(default_factory=list)
    length: Optional[int] = None

    @property
    def group(self) -> str:
        return self.path.split(SEPARATOR)[0]

    @property
    def name(self) -> str:
        """Name of the form control."""
        return FIELD_PREFIX + self.path.replace(SEPARATOR, "__")


def load_schema(repo_dir: str, relative: str) -> Dict[str, Any]:
    with open(
        os.path.join(repo_dir, "schemas", relative), "r", encoding="utf-8"
    ) as handle:
        return json.load(handle)


def _types(node: Dict[str, Any]) -> List[str]:
    t = node.get("type")
    if isinstance(t, list):
        return [x for x in t if x != "null"]
    return [t] if t else []


def _kind(node: Dict[str, Any]) -> Optional[str]:
    if "enum" in node:
        return "choice"
    types = _types(node)
    if "boolean" in types:
        return "bool"
    if "integer" in types:
        return "int"
    if "number" in types:
        return "float"
    if "string" in types:
        return "text"
    if "array" in types:
        items = node.get("items") or {}
        if _types(items) in (["number"], ["integer"]):
            return "numlist"
        return "json"
    if "object" in types:
        return "json"
    return None


def leaf_paths(schema: Dict[str, Any], prefix: str = "") -> List[str]:
    """Every setting of a schema: objects with ``properties`` are walked, anything else is a leaf."""
    out: List[str] = []
    for key, node in (schema.get("properties") or {}).items():
        path = f"{prefix}{key}"
        if (node.get("properties")) and not node.get("enum"):
            out.extend(leaf_paths(node, path + SEPARATOR))
        else:
            out.append(path)
    return out


def fields(
    schema: Dict[str, Any], internal: Iterable[str] = (), prefix: str = ""
) -> List[Field]:
    """The settings of a schema as form fields; ``internal`` paths are left out (YWeb sets them)."""
    skip = set(internal)
    out: List[Field] = []
    for key, node in (schema.get("properties") or {}).items():
        path = f"{prefix}{key}"
        if path in skip:
            continue
        if node.get("properties") and not node.get("enum"):
            out.extend(fields(node, skip, path + SEPARATOR))
            continue
        kind = _kind(node)
        if kind is None:
            continue
        out.append(
            Field(
                path=path,
                kind=kind,
                default=copy.deepcopy(node.get("default")),
                description=node.get("description", ""),
                minimum=node.get("minimum"),
                maximum=node.get("maximum"),
                exclusive_minimum=node.get("exclusiveMinimum"),
                choices=list(node.get("enum") or []),
                length=node.get("maxItems") or node.get("minItems"),
            )
        )
    return out


def coverage(
    schema: Dict[str, Any], internal: Iterable[str] = ()
) -> Tuple[List[str], List[str], List[str]]:
    """(exposed paths, internal paths, unknown internal paths): the three must account for the schema."""
    leaves = leaf_paths(schema)
    internal_set = set(internal)
    exposed = [f.path for f in fields(schema, internal_set)]
    unknown = sorted(internal_set - set(leaves))
    return exposed, sorted(internal_set & set(leaves)), unknown


# ------------------------------------------------------------------------------------ values
def apply_defaults(schema: Dict[str, Any], value: Any) -> Any:
    """``value`` with the defaults of ``schema`` filled in (objects completed recursively)."""
    if schema.get("type") == "object" or "properties" in schema:
        result = dict(value) if isinstance(value, dict) else {}
        for key, sub in (schema.get("properties") or {}).items():
            if key in result:
                result[key] = apply_defaults(sub, result[key])
            elif "default" in sub:
                default = copy.deepcopy(sub["default"])
                result[key] = (
                    apply_defaults(sub, default)
                    if isinstance(default, dict)
                    else default
                )
        return result
    return value


def defaults(schema: Dict[str, Any]) -> Dict[str, Any]:
    return apply_defaults(schema, {})


def get_path(data: Dict[str, Any], path: str, default: Any = None) -> Any:
    node: Any = data
    for part in path.split(SEPARATOR):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def set_path(data: Dict[str, Any], path: str, value: Any) -> None:
    node = data
    parts = path.split(SEPARATOR)
    for part in parts[:-1]:
        child = node.get(part)
        if not isinstance(child, dict):
            child = {}
            node[part] = child
        node = child
    node[parts[-1]] = value


def _number(raw: str, f: Field) -> float:
    try:
        number = float(str(raw).strip())
    except (TypeError, ValueError):
        raise ValueError("must be a number") from None
    if math.isnan(number) or math.isinf(number):
        raise ValueError("must be a finite number")
    return number


def _check_bounds(number: float, f: Field) -> None:
    if f.minimum is not None and number < f.minimum:
        raise ValueError(f"must be at least {f.minimum}")
    if f.maximum is not None and number > f.maximum:
        raise ValueError(f"must be at most {f.maximum}")
    if f.exclusive_minimum is not None and number <= f.exclusive_minimum:
        raise ValueError(f"must be greater than {f.exclusive_minimum}")


def parse_value(raw: Any, f: Field) -> Any:
    """Convert one submitted string to the type of the field (``ValueError`` with the reason)."""
    if f.kind == "bool":
        return str(raw).strip().lower() in ("1", "true", "on", "yes")
    text = "" if raw is None else str(raw).strip()
    if f.kind == "int":
        number = _number(text, f)
        if number != int(number):
            raise ValueError("must be an integer")
        _check_bounds(number, f)
        return int(number)
    if f.kind == "float":
        number = _number(text, f)
        _check_bounds(number, f)
        return number
    if f.kind == "choice":
        for choice in f.choices:
            if str(choice) == text:
                return choice
        raise ValueError("must be one of " + ", ".join(str(c) for c in f.choices))
    if f.kind == "numlist":
        parts = [p for p in text.replace(";", ",").split(",") if p.strip()]
        values = [_number(p, f) for p in parts]
        if f.length and len(values) != f.length and "hourly" in f.path:
            raise ValueError(f"needs {f.length} values")
        return values
    if f.kind == "json":
        if not text:
            return copy.deepcopy(f.default) if f.default is not None else {}
        try:
            return json.loads(text)
        except ValueError as exc:
            raise ValueError(f"not valid JSON ({exc})") from None
    return text


def to_form_text(value: Any, f: Field) -> str:
    """Value of a field as the text of its control."""
    if f.kind == "numlist" and isinstance(value, list):
        return ", ".join(str(v) for v in value)
    if f.kind == "json":
        return json.dumps(value if value is not None else {}, ensure_ascii=False)
    return "" if value is None else str(value)


def parse_form(
    form: Any, form_fields: Sequence[Field], label_of=lambda s: s
) -> Dict[str, Any]:
    """Nested dict of the values the form carries (a missing control keeps the default).

    A checkbox is always submitted with a hidden ``<name>__present`` control, so that unchecking it is a value.
    All problems are collected, each prefixed with the path of the setting.
    """
    out: Dict[str, Any] = {}
    problems: List[str] = []
    for f in form_fields:
        present = form.get(f.name + "__present")
        raw = form.get(f.name)
        if f.kind == "bool":
            if present is None and raw is None:
                continue
            set_path(out, f.path, parse_value(raw if raw is not None else "", f))
            continue
        if raw is None or (
            isinstance(raw, str) and raw.strip() == "" and f.kind != "text"
        ):
            continue
        try:
            set_path(out, f.path, parse_value(raw, f))
        except ValueError as exc:
            problems.append(f"{f.path}: {label_of(str(exc))}")
    if problems:
        raise SettingsError(problems)
    return out


def merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """``override`` laid over ``base`` (objects merged key by key)."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def schema_problems(schema: Dict[str, Any], value: Any) -> List[str]:
    """Problems of ``value`` against ``schema``, each prefixed with the path (empty = valid)."""
    import jsonschema

    validator = jsonschema.Draft7Validator(schema)
    return sorted(
        ("/".join(str(p) for p in e.absolute_path) or "<root>") + ": " + e.message
        for e in validator.iter_errors(value)
    )[:50]
