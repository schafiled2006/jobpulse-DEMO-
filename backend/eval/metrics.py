"""Stage 9 helpers: golden-set loader (tiny YAML reader, no new dependency)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

EVAL_DIR: Path = Path(__file__).resolve().parents[2] / "data" / "eval"
GOLDEN_SET_PATH: Path = EVAL_DIR / "golden_set.yaml"


def _strip_comment(line: str) -> str:
    in_single = in_double = False
    for i, ch in enumerate(line):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            return line[:i]
    return line


def load_golden_set(path: Path | str = GOLDEN_SET_PATH) -> list[dict[str, Any]]:
    """Read the golden set YAML (only this file's structure, no pyyaml)."""
    text = Path(path).read_text(encoding="utf-8")
    samples: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None
    in_expected = in_resume = False
    resume_lines: list[str] = []

    def flush() -> None:
        nonlocal in_resume
        if cur is not None and in_resume:
            cur["resume_text"] = " ".join(resume_lines).strip()
            resume_lines.clear()
            in_resume = False

    for raw in text.splitlines():
        line = _strip_comment(raw).rstrip()
        s = line.strip()
        if not s:
            continue
        if s.startswith(("version:", "created:", "notes:")) and cur is None:
            continue
        if s == "samples:":
            continue
        if s.startswith("- id:"):
            flush()
            cur = {"expected_job_ids": []}
            samples.append(cur)
            cur["id"] = s.split(":", 1)[1].strip().strip("\"'")
            in_expected = False
            continue
        if cur is None:
            continue
        if s.startswith("expected_job_ids:"):
            flush()
            inline = s.split(":", 1)[1].strip()
            if inline.startswith("["):
                cur["expected_job_ids"] = [
                    p.strip().strip("\"'") for p in inline.strip("[]").split(",") if p.strip()
                ]
                in_expected = False
            else:
                in_expected = True
            continue
        if in_expected and s.startswith("- "):
            cur["expected_job_ids"].append(s[2:].strip().strip("\"'"))
            continue
        if s.startswith("resume_text:"):
            flush()
            inline = s.split(":", 1)[1].strip()
            if inline.startswith((">", "|")):
                in_resume = True
            elif inline:
                cur["resume_text"] = inline.strip("\"'")
            in_expected = False
            continue
        if in_resume:
            if line[:1].isspace():
                resume_lines.append(s)
                continue
            flush()
        if s.startswith(("lang:", "domain:", "level:", "notes:", "id:")):
            k, _, v = s.partition(":")
            cur[k.strip()] = v.strip().strip("\"'")
            in_expected = False
    flush()
    return [x for x in samples if x.get("id") and x.get("resume_text") is not None]
