"""Release readiness: `contxt check` says whether a Contxt works and what to fix, and the web
app arrives from a release without Node.js, checked before anything is replaced."""

import hashlib
import io
import socket
import subprocess
import zipfile

import pytest

from workspace_server import cli, doctor, homes, webapp
from workspace_server.settings import Settings


def run(capsys, *argv):
    code = cli.main(["--env-file", "", *argv])
    return code, capsys.readouterr()


def zipped(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        for name, text in files.items():
            bundle.writestr(name, text)
    return buffer.getvalue()


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.fixture
def home(tmp_path):
    homes.create_home(str(tmp_path), homes.find_starter("programmer"), port=free_port())
    return tmp_path


def test_a_new_home_is_ready_and_says_what_would_make_it_better(home):
    settings = Settings.from_env(home=str(home))
    settings.web_dist = str(home / "no-web-app")
    checks = doctor.run(settings)
    states = {c.what.split(":")[0]: c.state for c in checks}
    assert not [c for c in checks if c.state == doctor.FAIL], doctor.render(checks)
    assert states["Kai's Dev Brain"] == doctor.OK
    assert any(c.what.startswith("AI apps can connect") and c.state == doctor.OK for c in checks)
    web = next(c for c in checks if "web app" in c.what)
    assert web.state == doctor.WARN and "contxt web --download" in web.fix
    assert doctor.render(checks).splitlines()[-1].startswith("Ready.")


def test_a_new_brain_starts_with_its_startup_files_committed(home):
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=home / "brain", capture_output=True, text=True, check=True
    ).stdout.split()
    assert "CLAUDE.md" in tracked and "AGENTS.md" in tracked


def test_check_without_a_brain_fails_with_the_fix(tmp_path, capsys):
    code, out = run(capsys, "--home", str(tmp_path), "check")
    assert code == 1
    assert "there is no Brain here yet" in out.out and "contxt setup" in out.out
    assert "Not ready" in out.out


def test_check_on_a_ready_home_exits_zero(home, capsys):
    code, out = run(capsys, "--home", str(home), "check")
    assert code == 0, out.out
    assert "the Brain keeps its own history" in out.out


def test_setup_takes_the_next_free_port_when_the_usual_one_is_taken():
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        taken = busy.getsockname()[1]
        assert homes.free_port(taken) > taken


def test_the_web_app_unpacks_whole_and_replaces_the_old_one(tmp_path):
    target = tmp_path / "dist"
    target.mkdir()
    (target / "index.html").write_text("old", encoding="utf-8")
    (target / "stale.js").write_text("old", encoding="utf-8")
    webapp.unpack(zipped({"index.html": "new", "assets/app.js": "js"}), str(target))
    assert (target / "index.html").read_text(encoding="utf-8") == "new"
    assert (target / "assets" / "app.js").exists() and not (target / "stale.js").exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["dist"]  # nothing left beside it


@pytest.mark.parametrize("files", [{"../escape.txt": "x", "index.html": "x"}, {"app.js": "x"}])
def test_a_bad_archive_changes_nothing(tmp_path, files):
    target = tmp_path / "dist"
    target.mkdir()
    (target / "index.html").write_text("old", encoding="utf-8")
    with pytest.raises(webapp.WebAppError, match="nothing was changed"):
        webapp.unpack(zipped(files), str(target))
    assert (target / "index.html").read_text(encoding="utf-8") == "old"
    assert not (tmp_path / "escape.txt").exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["dist"]


def test_the_download_is_checked_against_its_checksum(tmp_path, monkeypatch):
    archive = zipped({"index.html": "built"})
    good = hashlib.sha256(archive).hexdigest()
    asked = []

    def fake_get(url, *, token, accept, timeout=60):
        asked.append(url)
        return archive if url == "asset" else f"{checksum}  web-dist.zip\n".encode()

    monkeypatch.setattr(
        webapp,
        "release_assets",
        lambda repo, tag, token: {webapp.ASSET: "asset", webapp.CHECKSUM: "sum"},
    )
    monkeypatch.setattr(webapp, "_get", fake_get)
    target = tmp_path / "dist"

    checksum = "0" * 64
    with pytest.raises(webapp.WebAppError, match="checksum"):
        webapp.download(str(target), version="9.9.9", token="")
    assert not target.exists()

    checksum = good
    got = webapp.download(str(target), version="9.9.9", token="")
    assert got["tag"] == "v9.9.9" and got["sha256"] == good
    assert (target / "index.html").read_text(encoding="utf-8") == "built"


def test_a_token_is_never_sent_on_to_where_github_redirects(monkeypatch):
    seen = []

    class Reply(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(request, timeout):
        seen.append(request)
        return Reply(b"{}")

    monkeypatch.setattr(webapp.urllib.request, "urlopen", fake_urlopen)
    webapp._get("https://api.github.com/x", token="secret", accept="application/json")
    request = seen[0]
    assert request.unredirected_hdrs.get("Authorization") == "Bearer secret"
    assert "Authorization" not in request.headers


def test_without_a_build_the_server_says_how_to_get_one(owner):
    page = owner.client.get("/")
    assert page.status_code == 200 and "contxt web --download" in page.text
