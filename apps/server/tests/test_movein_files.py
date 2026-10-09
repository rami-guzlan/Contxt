"""Moving in reads files of any type, zips included: documents, instruction files, an AI app's
data export (the person's own messages), any text; what cannot be read is named with why."""

import io
import json
import zipfile

from workspace_server import movein_files
from workspace_server.movein_files import UploadReader

CHATGPT = [
    {
        "title": "Older chat",
        "update_time": 100,
        "mapping": {
            "a": {
                "message": {
                    "author": {"role": "user"},
                    "create_time": 1,
                    "content": {"parts": ["I run marketing alone."]},
                }
            },
            "b": {
                "message": {
                    "author": {"role": "assistant"},
                    "create_time": 2,
                    "content": {"parts": ["Noted."]},
                }
            },
        },
    },
    {
        "title": "Newer chat",
        "update_time": 200,
        "mapping": {
            "c": {
                "message": {
                    "author": {"role": "user"},
                    "create_time": 3,
                    "content": {"parts": ["Webinars start at 11 ET."]},
                }
            },
        },
    },
]
CLAUDE = [
    {
        "name": "Planning",
        "updated_at": "2026-10-01T10:00:00Z",
        "chat_messages": [
            {"sender": "human", "text": "Posts go out on Tuesdays."},
            {"sender": "assistant", "text": "Got it."},
        ],
    }
]


def zipped(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def test_a_zip_is_read_file_by_file_and_says_what_it_left_out():
    inner = zipped({"about.txt": b"I prefer short emails with one ask."})
    data = zipped(
        {
            "notes.md": b"# Notes\n\nOur fiscal year starts in July.",
            "CLAUDE.md": b"Never publish without approval.",
            ".cursor/rules/style.mdc": b"Use sentence case in headlines.",
            "export/conversations.json": json.dumps(CHATGPT).encode(),
            "logo.png": b"\x89PNG\r\n\x1a\n\x00\x00",
            "more.zip": inner,
            "__MACOSX/._notes.md": b"junk",
            ".DS_Store": b"junk",
        }
    )
    found = UploadReader().read([("memories.zip", data)])
    (source,) = found["sources"]
    assert source["label"] == "memories.zip"
    text = source["text"]
    for said in (
        "fiscal year starts in July",
        "Never publish without approval.",
        "sentence case",
        "Webinars start at 11 ET.",
        "short emails with one ask",
    ):
        assert said in text
    assert "# more.zip" in text and "Noted." not in text  # the person's words, not the AI's
    assert "junk" not in text
    assert found["skipped"] == [
        {"name": "memories.zip: logo.png", "why": "a picture: Moving in reads words, not images"}
    ]


def test_an_ai_apps_export_gives_the_persons_own_messages_newest_first():
    found = UploadReader().read(
        [
            ("conversations.json", json.dumps(CHATGPT).encode()),
            ("claude/conversations.json", json.dumps(CLAUDE).encode()),
        ]
    )
    chatgpt, claude = found["sources"]
    assert chatgpt["kind"] == "chatgpt"
    assert chatgpt["text"].index("Newer chat") < chatgpt["text"].index("Older chat")
    assert "Noted." not in chatgpt["text"]
    assert claude["kind"] == "claude" and "Posts go out on Tuesdays." in claude["text"]
    assert "Got it." not in claude["text"]


def test_other_json_text_and_what_cannot_be_read():
    other = {"profile": {"bio": "I lead learning at a mid-sized bank.", "id": "u_123456789012"}}
    found = UploadReader().read(
        [
            ("profile.json", json.dumps(other).encode()),
            ("rules", b"Answer in plain words, without hype."),
            ("call.m4a", b"\x00\x00\x00 ftypM4A"),
            ("budget.xlsx", b"PK\x03\x04 not really"),
            ("blob.bin", bytes(range(256)) * 4),
        ]
    )
    texts = [s["text"] for s in found["sources"]]
    assert texts == ["I lead learning at a mid-sized bank.", "Answer in plain words, without hype."]
    why = {s["name"]: s["why"] for s in found["skipped"]}
    assert why["call.m4a"].startswith("a recording")
    assert why["budget.xlsx"].startswith("a spreadsheet")
    assert why["blob.bin"] == "not a kind of file Moving in can read"


def test_limits_keep_a_zip_bomb_out_and_a_long_text_to_what_moving_in_takes(monkeypatch):
    monkeypatch.setattr(movein_files, "MAX_FILE", 50)
    data = zipped({"small.txt": b"Short and fine to read.", "big.txt": b"x " * 100})
    found = UploadReader().read([("both.zip", data)])
    assert "Short and fine" in found["sources"][0]["text"]
    assert found["skipped"] == [
        {"name": "both.zip: big.txt", "why": "it is too large to read here"}
    ]
    long = ("A sentence that repeats. " * 10_000).encode()
    (source,) = UploadReader().read([("long.txt", long)])["sources"]
    assert len(source["text"]) == movein_files.MAX_CHARS and source["note"]


def test_moving_in_reads_uploaded_files_then_previews_them(owner):
    data = zipped({"me.txt": b"I run marketing for a learning company.\nI prefer async reviews."})
    found = owner.ok(
        owner.client.post(
            "/api/brain/move-in/files",
            headers=owner.headers,
            files=[
                ("files", ("export.zip", data, "application/zip")),
                ("files", ("photo.jpg", b"\xff\xd8\xff", "image/jpeg")),
            ],
        )
    )
    (source,) = found["sources"]
    assert found["skipped"][0]["name"] == "photo.jpg"
    preview = owner.ok(
        owner.post(
            "/api/brain/move-in/preview",
            json={"sources": [{k: source[k] for k in ("kind", "label", "text")}]},
        )
    )
    assert preview["stages"]["ideas"] >= 2
