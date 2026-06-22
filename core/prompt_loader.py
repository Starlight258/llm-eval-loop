from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from typing import Any

from core.schemas import PromptDocument, PromptSpec


def _parse_scalar(value: str) -> Any:
    text = value.strip()
    if text.lower() in {"true", "false"}:
        return text.lower() == "true"
    if text.startswith('"') and text.endswith('"'):
        return text[1:-1]
    if text.startswith("'") and text.endswith("'"):
        return text[1:-1]
    if text.isdigit() or (text.startswith("-") and text[1:].isdigit()):
        return int(text)
    try:
        return float(text)
    except ValueError:
        return text


def parse_simple_yaml(text: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        index += 1
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in line:
            raise ValueError(f"Invalid prompt line: {line!r}")
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.lstrip()
        if value == "|":
            block: list[str] = []
            while index < len(lines):
                block_line = lines[index]
                if block_line.startswith("  "):
                    block.append(block_line[2:])
                    index += 1
                    continue
                if not block_line.strip():
                    block.append("")
                    index += 1
                    continue
                break
            data[key] = "\n".join(block).rstrip()
            continue
        data[key] = _parse_scalar(value)
    return data


def dump_simple_yaml(data: dict[str, Any]) -> str:
    lines: list[str] = []
    for key, value in data.items():
        if isinstance(value, bool):
            lines.append(f"{key}: {'true' if value else 'false'}")
        elif isinstance(value, int | float):
            lines.append(f"{key}: {value}")
        elif isinstance(value, str) and "\n" in value:
            lines.append(f"{key}: |")
            for row in value.splitlines():
                lines.append(f"  {row}")
        else:
            lines.append(f"{key}: {value}")
    return "\n".join(lines).rstrip() + "\n"


def prompt_version_label(label: str, raw_bytes: bytes) -> str:
    digest = sha256(raw_bytes).hexdigest()[:8]
    return f"{label}@{digest}"


def prompt_spec_to_dict(spec: PromptSpec) -> dict[str, Any]:
    return {
        "label": spec.label,
        "instructions": spec.instructions,
        "tone": spec.tone,
        "caution_level": spec.caution_level,
        "max_bullets": spec.max_bullets,
        "include_breakdowns": spec.include_breakdowns,
        "good_example": spec.good_example,
        "bad_example": spec.bad_example,
        "notes": spec.notes,
    }


def prompt_spec_to_text(spec: PromptSpec) -> str:
    return dump_simple_yaml(prompt_spec_to_dict(spec))


def spec_from_mapping(mapping: dict[str, Any]) -> PromptSpec:
    return PromptSpec(
        label=str(mapping.get("label", "")),
        instructions=str(mapping.get("instructions", "")),
        tone=str(mapping.get("tone", "balanced")),
        caution_level=str(mapping.get("caution_level", "balanced")),
        max_bullets=int(mapping.get("max_bullets", 4)),
        include_breakdowns=bool(mapping.get("include_breakdowns", True)),
        good_example=str(mapping.get("good_example", "")),
        bad_example=str(mapping.get("bad_example", "")),
        notes=str(mapping.get("notes", "")),
    )


def load_prompt_document(path: str | Path) -> PromptDocument:
    source_path = Path(path)
    raw_bytes = source_path.read_bytes()
    raw_text = raw_bytes.decode("utf-8")
    mapping = parse_simple_yaml(raw_text)
    spec = spec_from_mapping(mapping)
    version = prompt_version_label(spec.label, raw_bytes)
    return PromptDocument(
        label=spec.label,
        prompt_version=version,
        spec=spec,
        raw_text=raw_text,
        source_path=str(source_path),
    )


def build_prompt_document(spec: PromptSpec, source_path: str = "") -> PromptDocument:
    raw_text = prompt_spec_to_text(spec)
    raw_bytes = raw_text.encode("utf-8")
    version = prompt_version_label(spec.label, raw_bytes)
    return PromptDocument(
        label=spec.label,
        prompt_version=version,
        spec=spec,
        raw_text=raw_text,
        source_path=source_path,
    )


def update_prompt_spec(
    spec: PromptSpec,
    *,
    label: str | None = None,
    instructions: str | None = None,
    tone: str | None = None,
    caution_level: str | None = None,
    max_bullets: int | None = None,
    include_breakdowns: bool | None = None,
    good_example: str | None = None,
    bad_example: str | None = None,
    notes: str | None = None,
) -> PromptSpec:
    return replace(
        spec,
        label=label or spec.label,
        instructions=instructions if instructions is not None else spec.instructions,
        tone=tone or spec.tone,
        caution_level=caution_level or spec.caution_level,
        max_bullets=max_bullets if max_bullets is not None else spec.max_bullets,
        include_breakdowns=include_breakdowns if include_breakdowns is not None else spec.include_breakdowns,
        good_example=good_example if good_example is not None else spec.good_example,
        bad_example=bad_example if bad_example is not None else spec.bad_example,
        notes=notes if notes is not None else spec.notes,
    )

