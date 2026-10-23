"""A Contxt home: made from a starter Brain in one command, found from its folder, and
connected to any AI app with the text `contxt connect` prints."""

import json
import os
import subprocess
import sys

import pytest

from brainkit import gitops
from brainkit.api import Brain
from brainkit.index import Embedder
from workspace_connectors.providers import BRAIN_CLIENTS, brain_setup
from workspace_server import cli, homes
from workspace_server.settings import Settings

DEMOS = {"knowledge-company", "programmer", "entrepreneur", "personal"}


def git(folder, *args):
    return subprocess.run(
        ["git", *args], cwd=folder, capture_output=True, text=True, check=True
    ).stdout.strip()


def run(capsys, *argv):
    code = cli.main(["--env-file", "", *argv])
    return code, capsys.readouterr()


@pytest.fixture
def fetched(monkeypatch):
    """The meaning model's download, stood in: a test never reaches the network."""
    calls = []

    def download(self):
        calls.append(self.model_dir)
        os.makedirs(
            os.path.join(self.model_dir, "models--qdrant--bge-small-en-v1.5-onnx-q"), exist_ok=True
        )
        return {"available": True, "model": self.model_name, "reason": None, "loaded": False}

    monkeypatch.setattr(Embedder, "download", download)
    return calls


def test_the_starters_are_the_empty_brain_and_four_demos():
    found = homes.starters()
    assert found[0].id == "empty"
    assert {s.id for s in found} == {"empty"} | DEMOS
    assert all(s.name and s.description for s in found)


@pytest.mark.parametrize("starter", sorted({"empty"} | DEMOS))
def test_every_starter_is_a_healthy_brain(starter):
    """The engine's own check: no undeclared scopes or areas, every skill loads what exists,
    every pinned note is live. Demo content stays valid as it is edited."""
    brain = Brain(os.path.join(homes.find_starter(starter).path, "vault"), embeddings=False)
    try:
        report = brain.health().text
    finally:
        brain.close()
    assert "## Problems (0)" in report, report


def test_a_demo_brain_answers_with_its_own_context():
    vault = os.path.join(homes.find_starter("knowledge-company").path, "vault")
    brain = Brain(vault, embeddings=False)
    try:
        progress = brain.context("where are we on the webinar series?", record=False).data
        prices = brain.context("what does Brightmill sell and for how much?", record=False).data
    finally:
        brain.close()
    assert progress["focus_id"] == "q4-webinar-series"
    assert "company-offer" in prices["note_ids"]


def test_a_review_request_reaches_the_review_checklist():
    """A review or an audit is as often what a request is about as what it asks to do: the
    word stays among those a note is matched by, so "review this pull request" finds the code
    review checklist instead of nothing."""
    vault = os.path.join(homes.find_starter("programmer").path, "vault")
    brain = Brain(vault, embeddings=False)
    try:
        found = brain.context("Review this pull request for me", record=False).data
    finally:
        brain.close()
    assert found["mode"] != "lean"
    assert "practices-reviews-checklist" in found["note_ids"]


def test_a_home_is_made_from_a_starter_with_its_own_history(tmp_path):
    made = homes.create_home(str(tmp_path), homes.find_starter("programmer"), port=8800)
    assert os.path.isfile(os.path.join(made["vault"], "brain.json"))
    assert os.path.isdir(made["data"]) and os.path.isdir(made["outputs"])
    # The Brain is a git repository of its own, with the starter as its first commit.
    assert gitops.owns_repo(made["brain"])
    assert git(made["brain"], "log", "--format=%s") == "A new Brain from the programmer starter"
    assert not list(tmp_path.glob("brain/**/.gitkeep"))
    env = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "CONTXT_BRAIN_VAULT=brain/vault" in env and "CONTXT_PORT=8800" in env
    assert "CONTXT_NAME=Kai's Dev Brain" in env


@pytest.mark.skipif(os.name != "nt", reason="long paths are a Windows limit")
def test_a_new_home_enables_long_paths_on_windows(tmp_path):
    made = homes.create_home(str(tmp_path), homes.find_starter("personal"), port=8801)
    assert git(made["brain"], "config", "--local", "core.longpaths") == "true"


def test_a_home_that_holds_a_brain_is_never_overwritten(tmp_path):
    homes.create_home(str(tmp_path), homes.find_starter("empty"))
    before = (tmp_path / ".env").read_text(encoding="utf-8")
    with pytest.raises(homes.HomeError, match="nothing was changed"):
        homes.create_home(str(tmp_path), homes.find_starter("personal"))
    assert (tmp_path / ".env").read_text(encoding="utf-8") == before
    assert (
        json.loads((tmp_path / "brain" / "vault" / "brain.json").read_text(encoding="utf-8"))[
            "name"
        ]
        == "My Brain"
    )


def test_windows_zone_names_become_iana_zones():
    assert homes.iana_from_windows("Eastern Standard Time") == "America/New_York"
    assert homes.iana_from_windows("Mountain Standard Time\x00") == "America/Denver"
    assert homes.iana_from_windows("Somewhere Standard Time") is None
    zone = homes.local_timezone()
    assert zone is None or "/" in zone or zone == "UTC"


def test_an_unknown_starter_names_the_real_ones():
    with pytest.raises(homes.HomeError, match="knowledge-company"):
        homes.find_starter("chef")


def test_a_homes_settings_count_from_the_home(tmp_path, monkeypatch):
    homes.create_home(str(tmp_path), homes.find_starter("empty"), port=8811)
    monkeypatch.chdir(tmp_path.parent)  # run from anywhere: the home decides
    settings = Settings.from_env(home=str(tmp_path))
    assert settings.brain_vault == os.path.join(str(tmp_path), "brain", "vault")
    assert settings.data_dir == os.path.join(str(tmp_path), "data")
    assert settings.exports_dir == os.path.join(str(tmp_path), "outputs")
    assert settings.port == 8811 and settings.name == "My Brain"


def test_a_home_without_settings_is_still_found(tmp_path):
    homes.create_home(str(tmp_path), homes.find_starter("empty"))
    (tmp_path / ".env").unlink()
    settings = Settings.from_env(home=str(tmp_path))
    assert settings.brain_vault == os.path.join(str(tmp_path), "brain", "vault")
    assert settings.exports_dir == os.path.join(str(tmp_path), "outputs")


def test_the_current_folder_alone_is_never_taken_for_a_home(tmp_path, monkeypatch):
    homes.create_home(str(tmp_path), homes.find_starter("empty"))
    monkeypatch.chdir(tmp_path)
    settings = Settings.from_env("")  # no settings file, no home named
    assert settings.brain_vault is None and settings.exports_dir is None


def test_contxt_names_win_and_the_earlier_names_still_work(monkeypatch):
    monkeypatch.setenv("WORKSPACE_PORT", "9001")
    monkeypatch.setenv("WORKSPACE_NAME", "Earlier")
    assert Settings.from_env("").port == 9001
    monkeypatch.setenv("CONTXT_PORT", "9002")
    settings = Settings.from_env("")
    assert settings.port == 9002 and settings.name == "Earlier"


def test_setup_then_connect_from_the_command_line(tmp_path, capsys, fetched):
    code, out = run(capsys, "--home", str(tmp_path), "setup", "--brain", "entrepreneur")
    assert code == 0 and "Made a Brain from the entrepreneur starter" in out.out
    assert "contxt" in out.out and "connect" in out.out
    code, out = run(capsys, "--home", str(tmp_path), "setup")
    assert code == 1 and "nothing was changed" in out.err
    code, out = run(capsys, "--home", str(tmp_path), "connect", "codex")
    vault = os.path.join(str(tmp_path), "brain", "vault")
    assert code == 0 and "[mcp_servers.contxt]" in out.out and f"'{vault}'" in out.out
    code, out = run(capsys, "--home", str(tmp_path), "connect")
    assert code == 0 and all(f"== {label}" in out.out for label in BRAIN_CLIENTS.values())


def test_setup_fetches_the_meaning_model_unless_offline(tmp_path, capsys, fetched):
    # Recall falls from 88% to 77% on the demo set when the Brain matches by words alone.
    code, out = run(capsys, "--home", str(tmp_path / "online"), "setup")
    assert code == 0 and len(fetched) == 1
    assert "Your Brain matches requests by meaning" in out.out
    assert "models --download   also turn talk into text" in out.out
    code, out = run(capsys, "--home", str(tmp_path / "offline"), "setup", "--offline")
    assert code == 0 and len(fetched) == 1  # nothing more was fetched
    assert "models --download   match by meaning" in out.out


def test_setup_without_a_network_still_makes_the_brain(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(
        Embedder,
        "download",
        lambda self: {
            "available": False,
            "model": self.model_name,
            "reason": "no network",
            "loaded": False,
        },
    )
    code, out = run(capsys, "--home", str(tmp_path), "setup")
    assert code == 0 and "Made a Brain from the empty starter" in out.out
    assert "not set up yet (no network)" in out.out
    assert "models --download   match by meaning" in out.out


def test_connect_without_a_brain_says_how_to_make_one(tmp_path, capsys):
    code, out = run(capsys, "--home", str(tmp_path), "connect")
    assert code == 1 and "contxt setup" in out.err


def test_starters_lists_each_with_how_to_use_it(capsys):
    code, out = run(capsys, "starters")
    assert code == 0 and "knowledge-company" in out.out and "contxt demo" in out.out


def test_every_setup_runs_the_brain_this_environment_installed():
    vault = os.path.join("C:\\", "Users", "Pat Lee", "Contxt", "brain", "vault")
    python = sys.executable
    code = brain_setup("claude-code", python=python, vault=vault)
    assert code["command"].startswith("claude mcp add --scope user contxt -- ")
    assert f'"{vault}"' in code["command"]  # a path with a space arrives as one argument
    desktop = json.loads(brain_setup("claude-desktop", python=python, vault=vault)["config"])
    entry = desktop["mcpServers"]["contxt"]
    assert entry == {"command": python, "args": ["-m", "brainkit", "--vault", vault, "mcp"]}
    codex = brain_setup("codex", python=python, vault=vault)["config"]
    assert f"'{vault}'" in codex  # a TOML literal keeps backslashes as they are


def test_every_app_gets_the_instruction_that_makes_it_ask_first():
    """A model reads the Brain only when it calls gnomon_get_context, and it forgets most on a
    follow-up: connecting any app also says where to put a standing instruction to ask first."""
    vault = os.path.join("C:\\", "Contxt", "brain", "vault")
    setups = {c: brain_setup(c, python=sys.executable, vault=vault) for c in BRAIN_CLIENTS}
    instructions = {s["instruction"] for s in setups.values()}
    assert len(instructions) == 1  # one text, wherever it goes
    (text,) = instructions
    assert "gnomon_get_context" in text and "session_id" in text and "notes_propose" in text
    assert setups["claude-code"]["instruction_where"].startswith("~/.claude/CLAUDE.md")
    assert setups["codex"]["instruction_where"].startswith("~/.codex/AGENTS.md")
    assert "User Rules" in setups["cursor"]["instruction_where"]
    assert "personal preferences" in setups["claude-desktop"]["instruction_where"]
    assert all(s["instruction_where"] for s in setups.values())


def test_connect_prints_the_instruction_to_add(tmp_path, capsys, fetched):
    run(capsys, "--home", str(tmp_path), "setup")
    code, out = run(capsys, "--home", str(tmp_path), "connect", "codex")
    assert code == 0
    assert "Then add this to ~/.codex/AGENTS.md" in out.out
    assert "call gnomon_get_context with my message as I wrote it" in out.out


def test_the_app_shows_the_same_connection(owner, brain_vault):
    body = owner.ok(owner.get("/api/brain/connect"))
    assert body["ready"] and body["server"] == "contxt"
    assert body["vault"] == os.path.abspath(brain_vault)
    clients = {c["client"]: c for c in body["clients"]}
    assert set(clients) == set(BRAIN_CLIENTS)
    assert "-m brainkit --vault" in clients["claude-code"]["command"]
    assert "gnomon_get_context" in clients["cursor"]["instruction"]
