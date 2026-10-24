"""Gnomon's own n8n: installed (a pinned release) into the data folder, run on this computer
only, and given workflows through its own command line, with a restart to pick them up."""

import json
import os

from workspace_server.heartbeat import n8n as n8n_reads
from workspace_server.heartbeat.n8n_host import PINNED, N8nHost


class Done:
    def __init__(self, code=0, out="", err=""):
        self.returncode, self.stdout, self.stderr = code, out, err


class FakeProc:
    def __init__(self):
        self.stopped = False

    def poll(self):
        return 0 if self.stopped else None

    def terminate(self):
        self.stopped = True

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.stopped = True


class Machine:
    """npm, Node.js and n8n's command line as the host starts them."""

    def __init__(self, host_root):
        self.root = host_root
        self.runs = []
        self.starts = []
        self.imported = []

    def which(self, name):
        return f"/bin/{name}"

    def run(self, argv, **kwargs):
        self.runs.append({"argv": list(argv), "env": kwargs.get("env")})
        if "install" in argv:  # npm install puts n8n where the host looks for it
            entry = os.path.join(self.root, "app", "node_modules", "n8n", "bin")
            os.makedirs(entry, exist_ok=True)
            open(os.path.join(entry, "n8n"), "w").close()
        if any(a.startswith("--input=") for a in argv):
            path = next(a for a in argv if a.startswith("--input="))[len("--input=") :]
            with open(path, encoding="utf-8") as handle:
                self.imported.append(json.load(handle))
        return Done()

    def popen(self, argv, **kwargs):
        self.starts.append({"argv": list(argv), "env": kwargs.get("env")})
        return FakeProc()


def host(tmp_path):
    machine = Machine(str(tmp_path / "n8n"))
    made = N8nHost(
        str(tmp_path),
        popen=machine.popen,
        run=machine.run,
        which=machine.which,
        alive=lambda url: True,
    )
    return made, machine


def test_n8n_is_installed_once_from_a_pinned_release_into_gnomons_data_folder(tmp_path):
    n8n, machine = host(tmp_path)
    assert n8n.status()["installed"] is False
    n8n.install(wait=True)
    (npm,) = machine.runs
    assert npm["argv"][:3] == ["/bin/npm", "install", f"n8n@{PINNED}"]
    assert npm["argv"][npm["argv"].index("--prefix") + 1] == str(tmp_path / "n8n" / "app")
    assert n8n.status()["installed"] is True
    n8n.install(wait=True)
    assert len(machine.runs) == 1  # once


def test_n8n_runs_on_this_computer_only_and_stops_with_gnomon(tmp_path):
    n8n, machine = host(tmp_path)
    n8n.install(wait=True)
    n8n.start(wait=1)
    (started,) = machine.starts
    env = started["env"]
    assert env["N8N_LISTEN_ADDRESS"] == "127.0.0.1" and env["N8N_HOST"] == "127.0.0.1"
    assert env["N8N_DIAGNOSTICS_ENABLED"] == "false"
    assert env["N8N_USER_FOLDER"] == str(tmp_path / "n8n" / "home")
    assert n8n.status()["running"] is True
    n8n.close()
    assert n8n.status()["running"] is False


def test_a_workflow_goes_in_through_n8ns_command_line_and_n8n_restarts(tmp_path):
    n8n, machine = host(tmp_path)
    n8n.install(wait=True)
    n8n.start(wait=1)
    n8n.put_workflow({"id": "gnomon123", "nodes": []}, active=True)
    commands = [r["argv"][2] for r in machine.runs[1:]]
    assert commands == ["import:workflow", "update:workflow"]
    assert machine.runs[-1]["argv"][-1] == "--active=true"
    assert len(machine.starts) == 2  # restarted to pick it up


def test_n8ns_copy_posts_to_the_inbox_with_the_secret_and_keeps_a_stable_id():
    workflow = {
        "nodes": [
            {
                "name": "Post",
                "type": "n8n-nodes-base.httpRequest",
                "parameters": {"method": "POST", "url": "http://localhost:1/api/heartbeat/inbox/x"},
            }
        ]
    }
    copy = n8n_reads.prepare(workflow, "n8n:gmail", "http://127.0.0.1:8787", "s3cret")
    (node,) = copy["nodes"]
    assert node["parameters"]["url"] == "http://127.0.0.1:8787/api/heartbeat/inbox/n8n:gmail"
    header = node["parameters"]["headerParameters"]["parameters"][0]
    assert header == {"name": n8n_reads.SECRET_HEADER, "value": "s3cret"}
    assert copy["id"] == n8n_reads.prepare(workflow, "n8n:gmail", "x", "y")["id"]
    assert "s3cret" not in json.dumps(workflow)  # the original is left alone
