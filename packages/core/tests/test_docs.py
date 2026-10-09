"""The Workspace: docs from a template, links, both linked to projects without copying them; AI
only when asked (draft from a doc with a skill or an agent, push back on it, continue it), with
the doc pinned; what a run made taken as the next version, added at the end, or kept as a new
doc; and a doc brought in from a file or taken out as Markdown or Word."""

import io
import zipfile

import pytest

from workspace_core.errors import NotFound, ValidationFailed
from workspace_core.services.docs import TEMPLATES, excerpt

OUTLINE = "## The points, in order\n\n1. Polls run on Tuesdays.\n2. Video keeps its budget.\n"


class Reader:
    """The server's document reader, as far as these tests need it."""

    def extract(self, data, filename, mime):
        return data.decode()

    def markdown(self, data, filename):
        return f"# Brief\n\n{data.decode()}" if filename.endswith(".docx") else None


@pytest.fixture
def q4(brain):
    return brain.create_project(
        name="Q4 campaigns", summary="The fourth quarter", aliases=[], proposer="owner"
    )


@pytest.fixture
def launch(brain):
    return brain.create_project(name="Launch", summary="The launch", aliases=[], proposer="owner")


def _finish(ws, claude, task, *, title, text):
    claim = ws.bus.claim(claude, task.id)
    ws.skills.save_result(claude, run_id=claim.run.id, title=title, text=text)
    ws.bus.complete(claude, claim.run.id, summary="Done.")
    return claim


def test_a_doc_starts_blank_or_from_a_template_linked_to_its_projects(ws, owner, q4):
    blank = ws.docs.create(owner)
    assert (blank.capture, blank.body, blank.projects) == ("note", "", [])
    outline = ws.docs.create(owner, template="outline", projects=[q4.id])
    assert outline.title == "Outline" and "## The points, in order" in outline.body
    assert outline.projects == [q4.id]
    named = ws.docs.create(owner, template="plan", title="Webinar plan")
    assert named.title == "Webinar plan" and "## The steps" in named.body
    with pytest.raises(ValidationFailed, match="template"):
        ws.docs.create(owner, template="memo")
    with pytest.raises(NotFound, match="No project nope"):
        ws.docs.create(owner, projects=["nope"])
    view = ws.docs.items(owner)
    assert {i["id"] for i in view["items"]} == {blank.id, outline.id, named.id}
    (linked,) = [i for i in view["items"] if i["projects"]]
    assert linked["kind"] == "doc"
    assert linked["projects"] == [{"id": q4.id, "title": "Q4 campaigns", "missing": False}]
    assert [p["id"] for p in view["projects"]] == [q4.id]


def test_a_link_is_one_item_linked_from_either_side(ws, owner, q4, launch):
    calendar = ws.docs.link(owner, url="https://calendar.example.com/launch")
    assert (calendar.capture, calendar.url, calendar.title) == (
        "link",
        "https://calendar.example.com/launch",
        "calendar.example.com",
    )
    with pytest.raises(ValidationFailed):
        ws.docs.link(owner, url="javascript:alert(1)")
    ws.docs.set_projects(owner, calendar.id, [q4.id, launch.id])
    for project in (q4.id, launch.id):
        (item,) = ws.docs.items(owner, project=project)["items"]
        assert item["id"] == calendar.id and item["kind"] == "link" and item["excerpt"] == ""
    assert len(ws.docs.items(owner)["items"]) == 1  # one item, two labels, no copies
    ws.docs.set_projects(owner, calendar.id, [launch.id])
    assert ws.docs.items(owner, project=q4.id)["items"] == []
    ws.notes.archive(owner, calendar.id)
    assert ws.docs.items(owner)["items"] == []
    assert [i["id"] for i in ws.docs.items(owner, archived=True)["items"]] == [calendar.id]


def test_anything_linked_to_a_project_shows_with_the_agents_on_it(ws, owner, q4):
    talk = ws.notes.create(owner, title="Kickoff thoughts", body="Polls on Tuesdays.")
    ws.docs.set_projects(owner, talk.id, [q4.id])
    ws.agents.save(
        owner,
        "content-strategist",
        {"role": "Writes the posts", "projects": [q4.id]},
        "Write well.",
    )
    ws.agents.save(owner, "analyst", {"role": "Reads the numbers"}, "Count well.")
    view = ws.docs.items(owner, project=q4.id)
    assert [i["id"] for i in view["items"]] == [talk.id]
    assert view["agents"] == [
        {"name": "content-strategist", "role": "Writes the posts", "last_run": None}
    ]
    assert "agents" not in ws.docs.items(owner)


def test_push_back_asks_questions_and_writes_nothing_for_him(ws, owner, connect, q4):
    claude = connect()
    doc = ws.docs.create(owner, title="Q4 outline", projects=[q4.id])
    with pytest.raises(ValidationFailed, match="Write something first"):
        ws.docs.push_back(owner, doc.id)
    doc = ws.notes.save(owner, doc.id, body=OUTLINE)
    task = ws.docs.push_back(owner, doc.id)
    claim = _finish(ws, claude, task, title="Questions", text="1. Which polls? Readers will ask.")
    text = claim.packet["instructions"]["text"]
    assert "Do not rewrite it" in text and doc.id in text
    (pinned,) = claim.packet["inputs"]
    assert "Polls run on Tuesdays." in pinned["text"]
    (run,) = ws.docs.runs(owner, doc.id)
    assert run["doc_action"] == "push-back" and run["capture"]["id"] == doc.id
    assert run["result"]["text"] == "1. Which polls? Readers will ask."
    assert ws.notes.get(owner, doc.id).body == OUTLINE  # nothing written into the doc


def test_continue_adds_to_the_end_as_a_named_version(ws, owner, connect):
    claude = connect()
    doc = ws.docs.create(owner, title="Q4 outline")
    doc = ws.notes.save(owner, doc.id, body=OUTLINE)
    task = ws.docs.continue_(owner, doc.id, where="the last point")
    claim = _finish(ws, claude, task, title="More", text="3. Webinars move to spring.")
    assert "(from: the last point)" in claim.packet["instructions"]["text"]
    (run,) = ws.docs.runs(owner, doc.id)
    assert run["doc_action"] == "continue"
    taken = ws.docs.use(owner, doc.id, task_id=run["task_id"], how="append")
    assert taken.body.startswith("## The points, in order")
    assert taken.body.rstrip().endswith("2. Video keeps its budget.\n\n3. Webinars move to spring.")
    newest = ws.notes.versions(owner, doc.id)[0]
    assert (newest.label, newest.sealed) == ("From your AI", True)


def test_a_skill_drafts_from_the_outline_and_his_text_stays_in_versions(ws, owner, connect, q4):
    claude = connect()
    doc = ws.docs.create(owner, title="Q4 outline", projects=[q4.id])
    with pytest.raises(ValidationFailed, match="outline is enough"):
        ws.docs.draft(owner, doc.id, skill="weekly-posts")
    doc = ws.notes.save(owner, doc.id, body=OUTLINE)
    with pytest.raises(ValidationFailed, match="skill or an agent"):
        ws.docs.draft(owner, doc.id)
    task = ws.docs.draft(
        owner, doc.id, skill="weekly-posts", ask="A LinkedIn post from this outline."
    )
    claim = _finish(ws, claude, task, title="LinkedIn post", text="Polls are back on Tuesdays.")
    assert "A LinkedIn post from this outline." in claim.packet["instructions"]["text"]
    (pinned,) = claim.packet["inputs"]
    assert "Video keeps its budget." in pinned["text"]
    (run,) = ws.docs.runs(owner, doc.id)
    assert run["skill"] == "weekly-posts" and run["doc_action"] is None
    with pytest.raises(NotFound):
        ws.docs.use(owner, doc.id, task_id="task_nope", how="version")
    with pytest.raises(ValidationFailed):
        ws.docs.use(owner, doc.id, task_id=run["task_id"], how="replace")
    taken = ws.docs.use(owner, doc.id, task_id=run["task_id"], how="version")
    assert taken.body == "Polls are back on Tuesdays."
    newest, before, *_ = ws.notes.versions(owner, doc.id)
    assert (newest.label, newest.sealed) == ("From /weekly-posts", True)
    assert ws.notes.version(owner, doc.id, before.revision).body == OUTLINE
    edited = ws.notes.save(owner, doc.id, body="Polls are back on Tuesdays. Vote!")
    assert edited.revision == newest.revision + 1  # his next edit starts its own version


def test_an_agent_drafts_and_the_draft_can_be_kept_as_a_new_doc(ws, owner, connect, q4):
    claude = connect()
    ws.agents.save(owner, "content-strategist", {"role": "Writes the posts"}, "Write well.")
    doc = ws.docs.create(owner, title="Q4 outline", projects=[q4.id])
    doc = ws.notes.save(owner, doc.id, body=OUTLINE)
    task = ws.docs.draft(owner, doc.id, agent="content-strategist")
    claim = _finish(ws, claude, task, title="Three posts", text="One. Two. Three.")
    text = claim.packet["instructions"]["text"]
    assert "content-strategist" in text and "Draft it from my note “Q4 outline”." in text
    (run,) = ws.docs.runs(owner, doc.id)
    assert run["agent"] == "content-strategist"
    made = ws.docs.use(owner, doc.id, task_id=run["task_id"], how="new")
    assert (made.title, made.body, made.projects) == ("Three posts", "One. Two. Three.", [q4.id])
    assert ws.notes.get(owner, doc.id).body == OUTLINE


def test_a_file_comes_in_as_a_doc_to_work_in(ws, owner, q4):
    with pytest.raises(ValidationFailed, match="Bring in"):
        ws.docs.import_file(owner, filename="clip.mp3", data=b"ID3")
    with pytest.raises(ValidationFailed, match="no text"):
        ws.docs.import_file(owner, filename="Q4_brief.docx", data=b"PK")  # no reader yet
    ws.rt.extractor = Reader()
    doc = ws.docs.import_file(
        owner, filename="Q4_brief.docx", data=b"Who we reach.", projects=[q4.id]
    )
    assert (doc.title, doc.capture, doc.projects) == ("Q4 brief", "note", [q4.id])
    assert doc.body == "# Brief\n\nWho we reach."


def test_a_doc_leaves_as_markdown_or_word(ws, owner):
    doc = ws.docs.create(owner, title="Q4: the plan")
    ws.notes.save(
        owner, doc.id, body="## Goal\n\n- **More** sign-ups\n\n1. Polls\n\n> Keep it short."
    )
    name, media, data = ws.docs.export(owner, doc.id, fmt="md")
    assert (name, media) == ("Q4 the plan.md", "text/markdown; charset=utf-8")
    assert data.decode().startswith("# Q4: the plan\n\n## Goal")
    name, media, data = ws.docs.export(owner, doc.id, fmt="docx")
    assert name == "Q4 the plan.docx" and media.endswith("wordprocessingml.document")
    with zipfile.ZipFile(io.BytesIO(data)) as zipped:
        xml = zipped.read("word/document.xml").decode()
    for text in ("Q4: the plan", "Goal", "More", "sign-ups", "Polls", "Keep it short."):
        assert text in xml
    assert 'w:val="Title"' in xml and 'w:val="Heading2"' in xml and "<w:b/>" in xml
    with pytest.raises(ValidationFailed):
        ws.docs.export(owner, doc.id, fmt="pdf")


def test_an_excerpt_reads_as_words_and_an_untouched_template_says_nothing():
    for _, body in TEMPLATES.values():
        assert excerpt(body) == ""
    text = (
        "## Goal\n\nFill the **November** webinar.\n\n1. The problem.\n"
        "- [ ] book the room\n> Keep it short."
    )
    assert excerpt(text) == "Fill the November webinar. The problem. book the room Keep it short."
