"""The Library over REST: a web page and a GitHub repository fetched and kept whole, with where
they came from; written guides and uploaded documents; the kind and the refresh changed as a
decision; and fetching again, by hand (in at once) or on a schedule (waiting for a yes).
Nothing here touches the network: the page and git are stand-ins."""

import email.message
import os

import pytest

from workspace_server.library import LibraryWorker

PAGE = """<html><head><title>Field guide to sourdough</title></head><body>
<h1>Field guide to sourdough</h1><p>Feed the starter twice a day.</p>
<p>Bake when it doubles in four hours.</p></body></html>"""


class Response:
    def __init__(self, body, url, kind="text/html; charset=utf-8"):
        self.body = body.encode("utf-8")
        self.url = url
        self.headers = email.message.Message()
        self.headers["Content-Type"] = kind

    def geturl(self):
        return self.url

    def read(self, limit=-1):
        return self.body if limit < 0 else self.body[:limit]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class Web:
    """Pages by address; what each answers can change between fetches."""

    def __init__(self):
        self.pages = {"https://example.org/sourdough": (PAGE, "text/html; charset=utf-8")}

    def __call__(self, request):
        body, kind = self.pages[request.full_url]
        return Response(body, request.full_url, kind)


class Git:
    """A clone that writes a small repository, and the commands that would fetch it again."""

    def __init__(self):
        self.calls = []

    def __call__(self, argv):
        self.calls.append(argv[1:3])
        if argv[1] == "clone":
            folder = argv[-1]
            os.makedirs(os.path.join(folder, ".git"))
            os.makedirs(os.path.join(folder, "src", "components"))
            files = {
                "README.md": "# Site\n\nOur marketing site. Plain words, short pages.",
                "src/components/Button.tsx": "export const Button = () => <button>Go</button>;",
                ".env": "TOKEN=secret",
            }
            for rel, text in files.items():
                with open(os.path.join(folder, *rel.split("/")), "w", encoding="utf-8") as out:
                    out.write(text)
        if argv[-2:] == ["rev-parse", "HEAD"]:
            return "0123456789abcdef0123456789abcdef01234567\n"
        return ""


@pytest.fixture
def web(runtime):
    runtime.library.opener = Web()
    return runtime.library.opener


@pytest.fixture
def git(runtime):
    runtime.library.git = Git()
    return runtime.library.git


def keep_page(owner, **extra):
    body = {
        "url": "https://example.org/sourdough",
        "kind": "influence",
        "refresh": "weekly",
        **extra,
    }
    return owner.ok(owner.post("/api/library/url", json=body), 201)


def test_a_page_is_fetched_and_kept_with_where_it_came_from(owner, web):
    filed = keep_page(owner)
    assert filed["status"] == "applied", filed
    items = {i["path"]: i for i in owner.ok(owner.get("/api/library"))}
    item = items[filed["path"]]
    assert item["kind"] == "influence" and item["title"] == "Field guide to sourdough"
    assert item["source_url"] == "https://example.org/sourdough"
    assert item["refresh"] == "weekly" and item["fetched_at"]
    full = owner.ok(owner.get("/api/library/item", params={"path": filed["path"]}))
    assert "Feed the starter twice a day." in full["text"]
    assert "Source: https://example.org/sourdough" in full["text"]
    assert full["checked_at"]


def test_only_https_pages_of_text_are_fetched(owner, web):
    refused = owner.post("/api/library/url", json={"url": "http://example.org/sourdough"})
    assert refused.status_code == 422 and "https://" in refused.text
    web.pages["https://example.org/logo"] = ("PNG", "image/png")
    image = owner.post("/api/library/url", json={"url": "https://example.org/logo"})
    assert image.status_code == 422 and "not a page of text" in image.text


def test_a_repository_is_kept_as_a_snapshot_of_its_readme_tree_and_picked_files(owner, git):
    filed = owner.ok(
        owner.post(
            "/api/library/repo",
            json={"url": "https://github.com/acme/site", "paths": ["src/components/Button.tsx"]},
        ),
        201,
    )
    assert filed["status"] == "applied", filed
    full = owner.ok(owner.get("/api/library/item", params={"path": filed["path"]}))
    assert full["kind"] == "influence" and full["title"] == "acme/site"
    assert full["source_repo"] == "https://github.com/acme/site"
    assert full["source_paths"] == ["src/components/Button.tsx"]
    text = full["text"]
    assert "at commit 0123456789ab" in text and "Our marketing site." in text
    assert "## Folder tree" in text and "components/" in text
    assert "## src/components/Button.tsx" in text and "<button>Go</button>" in text
    assert "TOKEN=secret" not in text and ".env" not in text
    assert git.calls[0] == ["clone", "--depth"]


def test_a_secret_looking_file_is_never_read_from_a_repository(owner, git):
    refused = owner.post(
        "/api/library/repo", json={"url": "https://github.com/acme/site", "paths": [".env"]}
    )
    assert refused.status_code == 422 and "secret" in refused.text
    elsewhere = owner.post("/api/library/repo", json={"url": "https://gitlab.com/acme/site"})
    assert elsewhere.status_code == 422 and "GitHub" in elsewhere.text


def test_fetching_again_files_a_change_and_nothing_when_nothing_changed(owner, web):
    filed = keep_page(owner)
    web.pages["https://example.org/sourdough"] = (
        PAGE.replace("four hours", "five hours"),
        "text/html",
    )
    again = owner.ok(owner.post("/api/library/refresh", json={"path": filed["path"]}))
    assert again["status"] == "applied", again
    full = owner.ok(owner.get("/api/library/item", params={"path": filed["path"]}))
    assert "five hours" in full["text"]
    same = owner.ok(owner.post("/api/library/refresh", json={"path": filed["path"]}))
    assert same["status"] == "unchanged"


def test_an_item_due_on_its_schedule_waits_for_a_yes(owner, web, runtime):
    filed = keep_page(owner)
    runtime.library.checks.mark(filed["path"], "2026-01-01T00:00:00+00:00")
    web.pages["https://example.org/sourdough"] = (PAGE.replace("twice", "three times"), "text/html")
    assert LibraryWorker(runtime.ws, runtime.library).run_once() == 1
    full = owner.ok(owner.get("/api/library/item", params={"path": filed["path"]}))
    assert "twice a day" in full["text"]  # the change waits in Review
    waiting = owner.ok(owner.get("/api/brain/proposals"))
    assert any(p.get("target") == filed["path"] or filed["path"] in str(p) for p in waiting)
    assert LibraryWorker(runtime.ws, runtime.library).run_once() == 0  # checked: not due again


def test_the_kind_and_refresh_change_with_an_undo_point(owner, web):
    filed = keep_page(owner)
    changed = owner.ok(
        owner.put(
            "/api/library/item", json={"path": filed["path"], "kind": "guide", "refresh": "never"}
        )
    )
    assert (changed["kind"], changed["refresh"]) == ("guide", "never")
    assert changed["checkpoint"]


def test_a_guide_written_here_and_a_document_uploaded_are_kept_whole(owner):
    written = owner.ok(
        owner.post(
            "/api/library/write",
            json={"title": "How we write release notes", "text": "Lead with what changed."},
        ),
        201,
    )
    uploaded = owner.ok(
        owner.post(
            "/api/library/upload",
            files={"file": ("spec.md", b"# Spec\n\nThe app keeps every version.", "text/markdown")},
            data={"kind": "reference"},
        ),
        201,
    )
    kinds = {i["path"]: i["kind"] for i in owner.ok(owner.get("/api/library"))}
    assert kinds[written["path"]] == "guide" and kinds[uploaded["path"]] == "reference"


def test_an_asset_joins_the_library_with_where_it_came_from(owner, web):
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    filed = owner.ok(
        owner.post(
            "/api/library/upload",
            files={"file": ("logo.png", png, "image/png")},
            data={"kind": "asset", "title": "Logo"},
        ),
        201,
    )
    assert filed["status"] == "applied", filed
    items = {i["path"]: i for i in owner.ok(owner.get("/api/library"))}
    logo = items[filed["path"]]
    assert (logo["kind"], logo["file_kind"], logo["mime"]) == ("asset", "asset", "image/png")
    assert logo["origin"] == "library" and logo["origin_inferred"] is False
    full = owner.ok(owner.get("/api/library/item", params={"path": filed["path"]}))
    assert full["text"] is None  # an asset is shown or offered, never read as text
    page = keep_page(owner)
    assert items.get(page["path"]) is None  # filed after the list was read
    doc = owner.ok(owner.get("/api/library/item", params={"path": page["path"]}))
    assert doc["origin"] == "library" and "Feed the starter" in doc["text"]
    # An asset cannot become a guide; a document cannot become an asset.
    refused = owner.put("/api/library/item", json={"path": filed["path"], "kind": "guide"})
    assert refused.status_code == 422 and "asset's kind is asset" in refused.text
    refused = owner.put("/api/library/item", json={"path": page["path"], "kind": "asset"})
    assert refused.status_code == 422


def test_an_older_file_is_told_where_it_came_from_as_a_decision(owner):
    filed = owner.ok(
        owner.post("/api/brain/files", files={"file": ("plan.md", b"# Plan\n\nShip in May.")}),
        201,
    )
    assert filed["status"] == "applied", filed
    item = owner.ok(owner.get("/api/library/item", params={"path": filed["path"]}))
    assert item["origin"] == "upload"  # filed by a person in the app
    changed = owner.ok(
        owner.put("/api/library/item", json={"path": filed["path"], "origin": "capture:export"})
    )
    assert changed["origin"] == "capture:export" and changed["checkpoint"]
    wrong = owner.put("/api/library/item", json={"path": filed["path"], "origin": "nowhere"})
    assert wrong.status_code == 422 and "origin is one of" in wrong.text
