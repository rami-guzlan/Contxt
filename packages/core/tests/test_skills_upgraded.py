"""Skills, upgraded: one brought in from elsewhere applies at once with its files; each says when
it was last edited and used and what it loads that changed since; what uses it (skills, agents,
workflows); and skills worth writing down, from asks repeated with no skill to follow (alike by
meaning, or by words with no model here) and from prompts run often."""

import base64

import pytest

from workspace_core.errors import PermissionDenied, ValidationFailed
from workspace_core.ports import BrainSkill

SCRIPT = {"path": "scripts/make.py", "content_base64": base64.b64encode(b"print('hi')").decode()}


def test_a_skill_brought_in_applies_at_once_with_its_files(ws, owner, connect, brain):
    made = ws.skills.import_skill(
        owner,
        name="brand-sheet",
        category="design",
        description="A one-page brand sheet as a PDF.",
        body="# /brand-sheet\n\n1. Lay out the logo and colors.",
        artifacts=["pdf"],
        depends_on=["shared-assets"],
        files=[SCRIPT],
        source="a zip",
    )
    assert made["name"] == "brand-sheet" and made["replaced"] is False
    created = brain.proposed[-1]
    assert created["kind"] == "skill.create" and created["reason"] == "Brought in from a zip"
    assert created["target"]["files"] == [SCRIPT] and created["target"]["depends_on"] == [
        "shared-assets"
    ]
    assert created["target"]["category"] == "design"
    changed = ws.skills.import_skill(
        owner, name="weekly-posts", description="Posts.", body="# /weekly-posts\n\n1. Draft."
    )
    assert changed["replaced"] is True and brain.proposed[-1]["kind"] == "skill.update"
    with pytest.raises(ValidationFailed, match="no steps"):
        ws.skills.import_skill(owner, name="empty", description="x", body="  ")
    with pytest.raises(PermissionDenied):
        ws.skills.import_skill(connect(), name="sneaky", description="x", body="1. x")


def test_freshness_says_when_it_was_edited_and_used_and_what_changed(ws, owner, brain):
    brain.changed_loads = [
        {"key": "rules/voice", "title": "rules/voice", "at": "2026-09-20T09:00:00Z"}
    ]
    brain.request_rows = [
        {
            "at": "2026-09-25T09:00:00Z",
            "skill": "weekly-posts",
            "request": "posts please",
            "got": [],
        }
    ]
    fresh = ws.skills.freshness(owner, "weekly-posts")
    assert fresh["last_edited"] == "2026-09-01T10:00:00Z"
    assert fresh["changed"][0]["key"] == "rules/voice"
    assert fresh["last_asked"] == "2026-09-25T09:00:00Z" and fresh["last_run_here"] is None
    ws.skills.run(owner, "weekly-posts", ask="Three posts.")
    fresh = ws.skills.freshness(owner, "weekly-posts")
    assert fresh["last_run_here"] is not None and fresh["last_used"] == fresh["last_run_here"]


def test_what_uses_a_skill(ws, owner, brain):
    brain.extra_skills.append(
        BrainSkill(
            name="weekly-recap",
            category="social",
            description="Recap.",
            depends_on=["weekly-posts"],
        )
    )
    ws.agents.save(
        owner,
        "content-strategist",
        {"role": "Writes the posts", "skills": ["weekly-posts"]},
        "Write well.",
    )
    ws.workflows.save(
        owner,
        name="Posts",
        steps=[{"kind": "skill", "skill": "weekly-posts", "ask": "Three posts."}],
    )
    ws.workflows.save(owner, name="Other", steps=[{"kind": "prompt", "text": "Something else."}])
    users = ws.skill_users(owner, "weekly-posts")
    assert users["skills"] == ["weekly-recap"] and users["agents"] == ["content-strategist"]
    assert [w["name"] for w in users["workflows"]] == ["Posts"]


ASKS = [
    "Draft the weekly LinkedIn plan for the content team",
    "Draft our weekly LinkedIn plan for the content team please",
    "Weekly LinkedIn plan for the content team, draft it",
    "What did Jordan say about the webinar budget?",
]


def rows(texts, at="2026-09-27T10:00:00Z", skill=None):
    return [
        {"at": at, "skill": skill, "request": t, "app": "Claude Code", "got": []} for t in texts
    ]


def test_asks_repeated_with_no_skill_become_a_suggestion(ws, owner, brain):
    brain.request_rows = [
        *rows(ASKS),
        *rows(["Draft the weekly LinkedIn plan for the content team now"], skill="weekly-posts"),
        *rows(
            ["Draft the weekly LinkedIn plan for the content team again"], at="2026-08-01T10:00:00Z"
        ),
    ]
    found = ws.suggestions.list(owner)
    assert found["matched_by"] == "words"
    (one,) = found["suggestions"]
    assert (one["kind"], one["count"], one["apps"]) == ("asks", 3, ["Claude Code"])
    assert one["examples"][0] == ASKS[0] and one["ask"].startswith(
        "Write a skill for what I keep asking for"
    )
    ws.suggestions.dismiss(owner, one["key"])
    assert ws.suggestions.list(owner)["suggestions"] == []


def test_asks_are_matched_by_meaning_when_the_model_is_here(ws, owner, brain):
    texts = [
        "Plan next week's posts",
        "What should we post next week?",
        "Lay out the posts for the coming week",
        "Book the venue",
    ]
    brain.request_rows = rows(texts)
    # Three that mean the same point the same way; the fourth points elsewhere.
    brain.vectors = lambda batch: [
        [1.0, 0.05 * n] if "venue" not in t else [0.0, 1.0] for n, t in enumerate(batch)
    ]
    found = ws.suggestions.list(owner)
    assert found["matched_by"] == "meaning"
    (one,) = found["suggestions"]
    assert one["count"] == 3 and "Book the venue" not in one["examples"]


def test_a_prompt_run_often_becomes_a_suggestion(ws, owner, connect):
    connect()
    saved = ws.prompts.create(
        owner, title="Weekly posts", body="Three posts.", picks={"skills": ["weekly-posts"]}
    )
    for _ in range(3):
        ws.compose.run(owner, prompt_id=saved.id, request="Three posts.", skills=["weekly-posts"])
    (one,) = ws.suggestions.list(owner)["suggestions"]
    assert (one["kind"], one["count"], one["prompt_id"]) == ("prompt", 3, saved.id)
    assert one["ask"].startswith('Make a skill from my saved prompt "Weekly posts"')
