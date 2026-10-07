"""A small, deliberately non-marketing brain for engine tests: a design studio.

It exercises every structural feature: three scope levels with a custom `team:` prefix, two
people, two sealed client partitions, standing and on-demand notes, a digest, a Focus with a
journal, a skill with loads, a reference with a pointer note, routing hints and intents.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BRAIN = {
    "schema": 1,
    "name": "Northwind Studio Brain",
    "description": "Test brain for a small design studio.",
    "owner": "person:alex",
    "structure": {
        "scope_levels": [
            {"kind": "company", "label": "Company", "prefix": "", "container": ""},
            {"kind": "team", "label": "Team", "prefix": "team:", "container": "teams"},
            {"kind": "person", "label": "Person", "prefix": "person:", "container": "people",
             "principal": True},
        ],
        "partition_kinds": [
            {"kind": "client", "label": "Client", "prefix": "client:", "container": "clients"},
        ],
        "layers": {
            "identity": {"label": "Identity", "order": 1, "heading": "Identity"},
            "rules": {"label": "Rules", "order": 2, "heading": "Rules", "constraint": True},
            "facts": {"label": "Facts", "order": 3, "heading": "Core facts"},
            "state": {"label": "State", "order": 4, "heading": "Current state"},
        },
        "focus": {"layer": "state", "topic": "focus"},
    },
    "scopes": {
        "company": {"label": "Northwind"},
        "team:design": {"parent": "company", "label": "Design"},
        "person:alex": {"parent": "team:design", "label": "Alex"},
        "person:sam": {"parent": "company", "label": "Sam"},
    },
    "partitions": {
        "client:acme": {"owner": "person:alex", "label": "Acme"},
        "client:globex": {"owner": "person:alex", "label": "Globex"},
    },
    "governance": {"approver": "person:alex", "auto_apply_own_scope": True},
    "kernel": {"action_policy": "Never send anything to a client without Alex's approval."},
    "git": {"auto_commit": False},
}

TOPICS = """# Topics

## identity

identity/identity: who the assistant is for this studio

## rules

rules/style: how we write and design: plain language, headlines, grids
rules/delivery: what may go to a client and who approves it
rules/design: team design system rules such as the grid and spacing

## facts

facts/services: what the studio sells, timelines and pricing bands
facts/clients: per-client preferences and requirements
"""

ROUTING = {
    "house_style_topics": ["rules/style"],
    "permission_topics": ["rules/delivery"],
    "topics": {
        "facts/clients": {"requires_any": ["client", "clients", "acme", "globex"]},
        "rules/design": {"fit_terms": ["grid", "spacing", "layout"]},
    },
    "intents": [
        {"id": "billing-question", "match": {"any_terms": ["invoice", "invoices", "billing"]},
         "set": {"task_type": "knowledge"}, "include_topics": ["facts/services"]},
    ],
}


def note(note_id, layer, topic, scope, body, load="on-demand", **extra):
    meta = {"id": note_id, "layer": layer, "topic": topic, "scope": scope,
            "status": extra.pop("status", "approved"), "load": load}
    meta.update(extra)
    return meta, body


NOTES = [
    note("identity-001", "identity", "identity", "company",
         "You are Northwind Studio's assistant. Do the work, keep context, be plain.",
         load="standing", startup_text="Act as Northwind Studio's assistant: do the work, "
                                       "keep context, be plain."),
    note("rules-style-001", "rules", "style", "company",
         "Write in plain language with short sentences. No jargon, no hype words.",
         load="standing"),
    note("rules-style-002", "rules", "style", "company",
         "Headlines use sentence case, stay under nine words, and state one benefit."),
    note("rules-style-003", "rules", "style", "company",
         "Pointer: the full studio style guide lives at references/style-guide.md. Load it "
         "for long-form writing."),
    note("rules-delivery-001", "rules", "delivery", "company",
         "Never send client deliverables before Alex approves them. Stage drafts and wait.",
         load="standing", startup_text="Nothing goes to a client before Alex approves it."),
    note("rules-design-001", "rules", "design", "team:design",
         "Layouts use the 8px grid. Spacing tokens are multiples of eight."),
    note("facts-services-001", "facts", "services", "company",
         "Northwind offers brand identity, web design and motion design for small companies."),
    note("facts-services-002", "facts", "services", "company",
         "Web design projects run six to eight weeks from kickoff to launch; invoices go out "
         "at kickoff and at launch."),
    note("facts-clients-acme-001", "facts", "clients", "person:alex",
         "Acme prefers dark palettes and hates stock photography.", partition="client:acme"),
    note("facts-clients-globex-001", "facts", "clients", "person:alex",
         "Globex requires WCAG AA contrast on every screen.", partition="client:globex"),
    note("facts-sam-001", "facts", "services", "person:sam",
         "Sam's private note: prefers async reviews on Fridays."),
    note("facts-services-000", "facts", "services", "company",
         "Old pricing: everything cost one flat fee.", status="archived"),
    note("state-focus-website-redesign", "state", "focus", "person:alex",
         "Relaunch the Northwind site from the Figma prototype, with the new case studies.",
         project="Website Redesign", project_status="active",
         index_line="Northwind site relaunch from the Figma prototype"),
    note("state-focus-studio-podcast", "state", "focus", "person:alex",
         "A monthly podcast with guests from client teams.",
         project="Studio Podcast", project_status="paused",
         index_line="Monthly episodes with Quillfeather recording"),
]

SKILL = """---
name: brand-sheet
description: Produce a one-page brand sheet PDF with palette, type and voice for a client.
triggers:
  - create a brand sheet
  - build a brand one-pager
aliases:
  - brand sheet
artifacts:
  - pdf
loads:
  - rules/style
  - facts/services
  - references/style-guide.md
---
# /brand-sheet

1. Gather the palette and type choices.
2. Write the voice lines in plain language.
3. Export a one-page PDF.
"""

STYLE_GUIDE = "# Studio style guide\n\nLong-form guidance on writing and layout.\n"


FILES_WAIT = {"file": {"app": "wait", "chat": "wait", "folder": "wait"}}


def build(root=None, git=False, files_wait=False) -> str:
    """Materialize the fixture vault inside a new temp folder; returns the vault path.

    `files_wait` sets the capture policy so files wait for review, for tests of that path
    (by default the owner's files are filed at once)."""
    base = root or tempfile.mkdtemp(prefix="brain-test-")
    vault = os.path.join(base, "vault")
    os.makedirs(vault, exist_ok=True)
    shape = json.loads(json.dumps(BRAIN))
    if files_wait:
        shape["governance"]["capture"] = FILES_WAIT
    with open(os.path.join(vault, "brain.json"), "w", encoding="utf-8") as handle:
        json.dump(shape, handle, indent=2)
    with open(os.path.join(vault, "topics.md"), "w", encoding="utf-8") as handle:
        handle.write(TOPICS)
    with open(os.path.join(vault, "routing.json"), "w", encoding="utf-8") as handle:
        json.dump(ROUTING, handle, indent=2)
    import sys
    sys.path.insert(0, ROOT)
    from brainkit import frontmatter as fm
    from brainkit.vault import Vault
    v = Vault(vault)
    levels = BRAIN["structure"]["scope_levels"]
    kinds = BRAIN["structure"]["partition_kinds"]
    for meta, body in NOTES:
        v.write_note(v.note_path(meta, levels, kinds), dict(meta), body)
    skill_dir = os.path.join(vault, "skills", "design", "brand-sheet")
    os.makedirs(skill_dir, exist_ok=True)
    with open(os.path.join(skill_dir, "SKILL.md"), "w", encoding="utf-8") as handle:
        handle.write(SKILL)
    os.makedirs(os.path.join(vault, "references"), exist_ok=True)
    with open(os.path.join(vault, "references", "style-guide.md"), "w",
              encoding="utf-8") as handle:
        handle.write(STYLE_GUIDE)
    from brainkit import util
    util.append_jsonl(os.path.join(vault, "journal", "focus",
                                   "state-focus-website-redesign.jsonl"),
                      {"seq": 1, "at": "2026-09-01T10:00:00Z", "summary": "Prototype approved",
                       "changes": {"current": "Prototype approved; building pages",
                                   "next": "Write the case studies"}})
    del fm
    if git:
        _git(base, "init", "-q", "-b", "main")
        _git(base, "add", "-A")
        _git(base, "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-q",
             "-m", "fixture")
    return vault


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                   stdin=subprocess.DEVNULL)


def remove(vault):
    """Remove a vault made by build(), with the temp folder build() made for it: never a folder
    that holds anything else (the temp folder itself, which a test's own mkdtemp sits in)."""
    vault = os.path.abspath(vault)
    base = os.path.dirname(vault)
    temp = os.path.abspath(tempfile.gettempdir())
    if os.path.basename(vault) != "vault" or os.path.normcase(base) == os.path.normcase(temp):
        raise ValueError(f"fixture.remove takes a vault made by fixture.build(), not {vault}")
    shutil.rmtree(base, ignore_errors=True)
