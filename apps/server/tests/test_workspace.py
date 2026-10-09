"""The Workspace over REST, on the sample Brain: a doc from a template and a link, both linked to
a project and listed by it; push back on a doc and continue it, with the doc pinned to the run,
and take what a run made; and a doc out as Word and back in as a new doc, its text intact."""

OUTLINE = "## The points\n\n1. Reviews run on Fridays.\n2. **Video** keeps its budget.\n"


def new_project(owner, name="Q4 campaigns"):
    made = owner.ok(
        owner.post("/api/brain/projects", json={"name": name, "summary": "The work"}), 201
    )
    return made["id"]


def written(owner, *, projects=(), body=OUTLINE, title="Q4 outline"):
    doc = owner.ok(
        owner.post("/api/workspace/docs", json={"title": title, "projects": list(projects)}), 201
    )
    return owner.ok(owner.put(f"/api/notes/{doc['id']}", json={"body": body}))


def finish(model, task, *, title, text):
    claim = model.tool("claim_task", task_id=task["id"])["structuredContent"]
    saved = model.tool("save_skill_result", run_id=claim["run"]["id"], title=title, text=text)
    assert not saved.get("isError"), saved
    model.tool("complete_task", run_id=claim["run"]["id"], summary="Done.")
    return claim


def test_docs_and_links_are_kept_by_project(owner):
    q4 = new_project(owner)
    doc = owner.ok(
        owner.post("/api/workspace/docs", json={"template": "outline", "projects": [q4]}), 201
    )
    assert (doc["title"], doc["projects"], doc["capture"]) == ("Outline", [q4], "note")
    link = owner.ok(
        owner.post(
            "/api/workspace/links",
            json={"url": "https://calendar.example.com/q4", "title": "Q4 calendar"},
        ),
        201,
    )
    assert (link["capture"], link["url"], link["title"]) == (
        "link",
        "https://calendar.example.com/q4",
        "Q4 calendar",
    )
    assert owner.post("/api/workspace/docs", json={"template": "memo"}).status_code == 422
    assert owner.post("/api/workspace/docs", json={"projects": ["nope"]}).status_code == 404
    assert (
        owner.post("/api/workspace/links", json={"url": "ftp://files.example.com/x"}).status_code
        == 422
    )
    owner.ok(owner.put(f"/api/workspace/{link['id']}/projects", json={"projects": [q4]}))
    view = owner.ok(owner.get("/api/workspace/items", params={"project": q4}))
    assert {i["id"] for i in view["items"]} == {doc["id"], link["id"]}
    assert view["agents"] == []
    everything = owner.ok(owner.get("/api/workspace/items"))
    assert "agents" not in everything and q4 in [p["id"] for p in everything["projects"]]
    owner.ok(owner.post(f"/api/notes/{link['id']}/archive"))
    set_aside = owner.ok(owner.get("/api/workspace/items", params={"archived": "true"}))
    assert [i["id"] for i in set_aside["items"]] == [link["id"]]


def test_push_back_and_continue_run_with_the_doc_pinned(owner, model):
    doc = written(owner)
    task = owner.ok(owner.post(f"/api/workspace/{doc['id']}/push-back"), 201)
    claim = finish(model, task, title="Questions", text="1. Which reviews? Clients will ask.")
    assert "Do not rewrite it" in claim["packet"]["instructions"]["text"]
    assert "Reviews run on Fridays." in claim["packet"]["inputs"][0]["text"]
    task = owner.ok(
        owner.post(f"/api/workspace/{doc['id']}/continue", json={"where": "the end"}), 201
    )
    finish(model, task, title="More", text="3. Webinars move to spring.")
    runs = owner.ok(owner.get(f"/api/workspace/{doc['id']}/runs"))
    assert [r["doc_action"] for r in runs] == ["continue", "push-back"]
    taken = owner.ok(
        owner.post(
            f"/api/workspace/{doc['id']}/use", json={"task_id": runs[0]["task_id"], "how": "append"}
        ),
    )
    assert taken["body"].rstrip().endswith("3. Webinars move to spring.")
    versions = owner.ok(owner.get(f"/api/notes/{doc['id']}/versions"))
    assert versions[0]["label"] == "From your AI"
    missing = owner.post(
        f"/api/workspace/{doc['id']}/use", json={"task_id": "task_nope", "how": "new"}
    )
    assert missing.status_code == 404


def test_a_draft_from_a_skill_needs_words_and_a_skill(owner):
    empty = owner.ok(owner.post("/api/workspace/docs", json={}), 201)
    refused = owner.post(f"/api/workspace/{empty['id']}/draft", json={"skill": "brand-sheet"})
    assert refused.status_code == 422 and "outline is enough" in refused.text
    doc = written(owner)
    assert owner.post(f"/api/workspace/{doc['id']}/draft", json={}).status_code == 422
    assert (
        owner.post(f"/api/workspace/{doc['id']}/draft", json={"agent": "nobody"}).status_code == 404
    )


def test_a_doc_goes_out_as_word_and_comes_back_in_as_a_doc(owner):
    q4 = new_project(owner)
    doc = written(owner, title="Q4: the outline")
    markdown = owner.get(f"/api/workspace/{doc['id']}/export", params={"format": "md"})
    assert markdown.status_code == 200 and markdown.text.startswith(
        "# Q4: the outline\n\n## The points"
    )
    word = owner.get(f"/api/workspace/{doc['id']}/export", params={"format": "docx"})
    assert word.status_code == 200 and word.content[:2] == b"PK"
    assert "wordprocessingml" in word.headers["content-type"]
    assert 'filename="Q4 the outline.docx"' in word.headers["content-disposition"]
    assert (
        owner.get(f"/api/workspace/{doc['id']}/export", params={"format": "pdf"}).status_code == 422
    )
    back = owner.ok(
        owner.post(
            "/api/workspace/import",
            files={"file": ("Q4 the outline.docx", word.content, "application/octet-stream")},
            data={"projects": q4},
        ),
        201,
    )
    assert back["projects"] == [q4] and back["capture"] == "note"
    for text in ("The points", "Reviews run on Fridays.", "Video", "keeps its budget."):
        assert text in back["body"]
    clip = owner.post("/api/workspace/import", files={"file": ("clip.mp3", b"ID3", "audio/mpeg")})
    assert clip.status_code == 422
