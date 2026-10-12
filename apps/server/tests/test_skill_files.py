"""Skills as files, on the sample Brain: brought in from a zip, a picked folder or a GitHub
repository (what the Brain does not keep is skipped and said); taken away as a zip; copied into
Claude Code with a stamp of the version that went; and what uses each skill, when it was edited
and used, and the skills worth writing down."""

import io
import json
import os
import zipfile

from workspace_server import skill_files

SKILL = """---
name: brand-voice
description: Check a draft against the studio's voice and fix what drifts.
---
# Brand voice

1. Read the draft.
2. Mark what is off the voice, and fix it.
"""


def zipped(files: dict[str, bytes]) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return out.getvalue()


def test_a_zip_comes_in_with_its_files_and_says_what_it_skipped(owner):
    data = zipped(
        {
            "brand-voice/SKILL.md": SKILL.encode(),
            "brand-voice/scripts/check.py": b"print('ok')",
            "brand-voice/.env": b"TOKEN=nope",
            "brand-voice/tool.exe": b"MZ",
        }
    )
    made = owner.ok(
        owner.post(
            "/api/skills/import", files={"file": ("brand-voice.zip", data, "application/zip")}
        ),
        201,
    )
    assert (made["name"], made["replaced"], made["files"]) == ("brand-voice", False, 1)
    assert sorted(s.split(":")[0] for s in made["skipped"]) == [".env", "tool.exe"]
    cards = {c["name"]: c for c in owner.ok(owner.get("/api/skills"))["skills"]}
    assert cards["brand-voice"]["description"].startswith("Check a draft")
    two = zipped({"a/SKILL.md": SKILL.encode(), "b/SKILL.md": SKILL.encode()})
    refused = owner.post("/api/skills/import", files={"file": ("two.zip", two, "application/zip")})
    assert refused.status_code == 422 and "one at a time" in refused.text
    none = owner.post(
        "/api/skills/import", files={"file": ("x.zip", zipped({"a.txt": b"x"}), "application/zip")}
    )
    assert none.status_code == 422 and "no SKILL.md" in none.text


def test_a_picked_folder_comes_in_and_the_skill_goes_out_as_a_zip(owner):
    made = owner.ok(
        owner.post(
            "/api/skills/import",
            files=[
                ("files", ("SKILL.md", SKILL.encode(), "text/markdown")),
                ("files", ("tone.md", b"# Tone\nWarm.", "text/markdown")),
            ],
            data={"paths": ["brand-voice/SKILL.md", "brand-voice/references/tone.md"]},
        ),
        201,
    )
    assert made["name"] == "brand-voice" and made["files"] == 1
    out = owner.get("/api/skills/brand-voice/export")
    assert (
        out.status_code == 200
        and 'filename="brand-voice.zip"' in out.headers["content-disposition"]
    )
    names = zipfile.ZipFile(io.BytesIO(out.content)).namelist()
    assert "brand-voice/SKILL.md" in names and "brand-voice/references/tone.md" in names


def test_a_skill_comes_in_from_a_github_repository(owner, monkeypatch):
    seen = []

    def fake_git(argv):
        seen.append(argv)
        if argv[1] == "clone":
            folder = os.path.join(argv[-1], "skills", "brand-voice")
            os.makedirs(folder, exist_ok=True)
            with open(os.path.join(folder, "SKILL.md"), "w", encoding="utf-8") as handle:
                handle.write(SKILL)
        return ""

    monkeypatch.setattr(skill_files, "_git", fake_git)
    made = owner.ok(
        owner.post(
            "/api/skills/import/git",
            json={"url": "https://github.com/acme/skills/tree/main/skills/brand-voice"},
        ),
        201,
    )
    assert made["name"] == "brand-voice"
    assert (
        seen[0][:4] == ["git", "clone", "--depth", "1"]
        and seen[0][-2] == "https://github.com/acme/skills.git"
    )
    bad = owner.post("/api/skills/import/git", json={"url": "https://gitlab.com/acme/skills"})
    assert bad.status_code == 422


def test_a_copy_goes_to_claude_code_with_its_version_stamped(owner, tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    pushed = owner.ok(
        owner.post("/api/skills/brand-sheet/push", json={"project_dir": str(project)})
    )
    place = project / ".claude" / "skills" / "brand-sheet"
    assert pushed["place"] == str(place) and pushed["behind"] == 0
    assert (place / "SKILL.md").exists()
    stamp = json.loads((place / skill_files.STAMP).read_text(encoding="utf-8"))
    assert stamp["skill"] == "brand-sheet" and stamp["hash"]
    about = owner.ok(owner.get("/api/skills/brand-sheet/about"))
    (copy,) = [p for p in about["pushed"] if p["place"] == str(place)]
    assert copy["behind"] == 0 and copy["user"] is False
    assert set(about) == {"used_by", "freshness", "pushed"}
    assert "last_edited" in about["freshness"] and about["used_by"]["agents"] == []
    other = tmp_path / "other"
    (other / ".claude" / "skills" / "brand-sheet").mkdir(parents=True)
    refused = owner.post("/api/skills/brand-sheet/push", json={"project_dir": str(other)})
    assert refused.status_code == 409 and "did not come from Contxt" in refused.text


def test_the_skills_page_shows_each_skill_by_purpose_with_how_it_stands(owner, model):
    """Your skills by purpose (UX C): each with when it was last used, whether it may be out of
    date, what uses it, its version and its Claude Code copy, in one call."""
    found = {s["name"]: s for s in owner.ok(owner.get("/api/skills/overview"))}
    sheet = found["brand-sheet"]
    assert set(sheet) == {
        "name",
        "category",
        "last_used",
        "last_edited",
        "changed",
        "version",
        "used_by",
        "copy",
    }
    assert sheet["version"] >= 1 and isinstance(sheet["changed"], list)
    assert sheet["used_by"]["agents"] == [] and sheet["copy"] is None
    assert model.get("/api/skills/overview").status_code in (200, 403)


def test_suggestions_answer_even_with_nothing_to_suggest(owner):
    found = owner.ok(owner.get("/api/skills/suggestions"))
    assert found["suggestions"] == [] and found["matched_by"] in ("meaning", "words")
    owner.ok(owner.post("/api/skills/suggestions/dismiss", json={"key": "asks:abc"}), 204)
