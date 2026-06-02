#!/usr/bin/env python3
"""Validate every SKILL.md has required frontmatter keys."""

import re
import sys
from pathlib import Path

REQUIRED_KEYS = ["name", "description"]
ROOT = Path(__file__).resolve().parent.parent

errors: list[str] = []
checked = 0
for skill_md in (ROOT / "skills").rglob("SKILL.md"):
    checked += 1
    text = skill_md.read_text()
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not m:
        errors.append(f"{skill_md.relative_to(ROOT)}: missing frontmatter block")
        continue
    frontmatter = m.group(1)
    found = {
        line.split(":", 1)[0].strip()
        for line in frontmatter.split("\n")
        if ":" in line and not line.startswith(" ")
    }
    missing = [k for k in REQUIRED_KEYS if k not in found]
    if missing:
        errors.append(f"{skill_md.relative_to(ROOT)}: missing keys {missing}")

if errors:
    for e in errors:
        print(f"ERROR: {e}", file=sys.stderr)
    sys.exit(1)

print(f"OK: {checked} SKILL.md files valid.")
