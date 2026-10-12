"""Test the Brain, server side: the results contract, the runner and who may use it.

A stub Lab (tests/stub_lab) keeps the contract the way a real runner would, with invented
content. Nothing here loads a person's settings: conftest clears every CONTXT_ and WORKSPACE_
variable, and the tests that need some set them on purpose.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import sys
import time

import pytest

from workspace_server import lab_contract
from workspace_server.lab_contract import ContractError, parse_contract

STUB = os.path.join(os.path.dirname(__file__), "stub_lab", "lab_stub.py")
PREFIX = "/api/test-the-brain"


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle)


def read_json(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def make_lab(folder, *, contract=None):
    """A stub Lab in `folder`: its runner, a launcher beside it, and a contract."""
    bin_dir = os.path.join(folder, "bin")
    os.makedirs(bin_dir, exist_ok=True)
    shutil.copy(STUB, os.path.join(bin_dir, "lab_stub.py"))
    if os.name == "nt":
        launcher = "lab.cmd"
        body = '@echo off\r\n"%LAB_PYTHON%" "%~dp0lab_stub.py" %*\r\n'
    else:
        launcher = "lab"
        body = '#!/bin/sh\nexec "$LAB_PYTHON" "$(dirname "$0")/lab_stub.py" "$@"\n'
    path = os.path.join(bin_dir, launcher)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(body)
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP)
    data = {
        "contract": 1,
        "name": "Stub Lab",
        "results": "results",
        "runner": {"exe": f"bin/{launcher}", "cwd": "."},
        "env_allow": ["LAB_PYTHON", "LAB_CONFIG", "LAB_STUB_DELAY"],
    }
    data.update(contract or {})
    write_json(os.path.join(folder, "lab.contract.json"), data)
    return folder


@pytest.fixture
def lab(tmp_path, monkeypatch):
    monkeypatch.setenv("LAB_PYTHON", sys.executable)
    monkeypatch.setenv("LAB_CONFIG", "stub-config")
    monkeypatch.setenv("LAB_STUB_DELAY", "0.01")
    return make_lab(str(tmp_path / "lab"))


@pytest.fixture
def connected(owner, lab):
    owner.ok(owner.post(f"{PREFIX}/lab", json={"folder": lab}))
    return lab


def wait_for(check, *, timeout=30.0, what="the run"):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        found = check()
        if found:
            return found
        time.sleep(0.05)
    raise AssertionError(f"Timed out waiting for {what}")


def finished(owner):
    live = owner.ok(owner.get(f"{PREFIX}/live"))
    active = live["active"]
    return live if active and active["state"] != "running" else None


def alive(pid: int) -> bool:
    if os.name == "nt":
        import ctypes

        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        code = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(handle)
        return code.value == 259
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def tree_listing(folder):
    out = {}
    for base, _dirs, files in os.walk(folder):
        for name in files:
            path = os.path.join(base, name)
            out[os.path.relpath(path, folder)] = os.path.getsize(path)
    return out


# ------------------------------------------------------------------ the contract
def good(**changes):
    data = {"contract": 1, "runner": {"exe": "bin/lab"}}
    data.update(changes)
    return data


def test_an_unknown_contract_version_is_refused_in_plain_words():
    with pytest.raises(ContractError) as caught:
        parse_contract(good(contract=2))
    message = str(caught.value)
    assert "contract 2" in message and "does not know" in message and "guessed" in message


def test_a_contract_without_a_version_number_is_refused():
    for data in ({"runner": {"exe": "x"}}, good(contract="1"), good(contract=True), []):
        with pytest.raises(ContractError):
            parse_contract(data)


def test_a_contract_cannot_ask_for_the_apps_own_settings(monkeypatch):
    for name in ("CONTXT_DATA_DIR", "workspace_owner_token", "CONTXT_"):
        with pytest.raises(ContractError, match="never receives"):
            parse_contract(good(env_allow=[name]))
    with pytest.raises(ContractError, match="not a variable name"):
        parse_contract(good(env_allow=["A=B"]))


def test_the_runner_must_be_inside_the_labs_folder(tmp_path):
    folder = make_lab(str(tmp_path / "lab"))
    outside = tmp_path / "evil.exe"
    outside.write_text("x")
    for exe in (
        "../evil.exe",
        "bin/../../evil.exe",
        str(outside),
        "/etc/passwd",
        "C:\\Windows\\x.exe",
    ):
        write_json(
            os.path.join(folder, "lab.contract.json"),
            good(runner={"exe": exe}),
        )
        with pytest.raises(ContractError, match="Lab's folder"):
            lab_contract.open_lab(folder)
    write_json(
        os.path.join(folder, "lab.contract.json"),
        good(runner={"exe": "bin/lab_stub.py", "cwd": ".."}),
    )
    with pytest.raises(ContractError, match="leaves the Lab's folder"):
        lab_contract.open_lab(folder)
    write_json(
        os.path.join(folder, "lab.contract.json"),
        good(results="../elsewhere", runner={"exe": "bin/lab_stub.py"}),
    )
    with pytest.raises(ContractError, match="leaves the Lab's folder"):
        lab_contract.open_lab(folder)


def test_a_runner_that_is_a_link_out_of_the_lab_is_refused(tmp_path):
    folder = make_lab(str(tmp_path / "lab"))
    target = tmp_path / "outside.py"
    target.write_text("print(1)")
    link = os.path.join(folder, "bin", "linked")
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError):
        pytest.skip("this machine does not allow symbolic links")
    write_json(os.path.join(folder, "lab.contract.json"), good(runner={"exe": "bin/linked"}))
    with pytest.raises(ContractError, match="leaves the Lab's folder"):
        lab_contract.open_lab(folder)


def test_connecting_refuses_a_bad_folder_and_says_what_to_do(owner, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    reply = owner.post(f"{PREFIX}/lab", json={"folder": str(empty)})
    assert reply.status_code == 422 and "lab.contract.json" in reply.text
    reply = owner.post(f"{PREFIX}/lab", json={"folder": str(tmp_path / "nowhere")})
    assert reply.status_code == 422 and "Pick the Lab's folder" in reply.text
    bad = make_lab(str(tmp_path / "newer"), contract={"contract": 7})
    reply = owner.post(f"{PREFIX}/lab", json={"folder": bad})
    assert reply.status_code == 422 and "contract 7" in reply.text


def test_a_lab_inside_the_apps_own_folders_is_refused(owner, runtime):
    inside_data = make_lab(os.path.join(runtime.settings.data_dir, "lab"))
    reply = owner.post(f"{PREFIX}/lab", json={"folder": inside_data})
    assert reply.status_code == 422 and "this app's own" in reply.text
    inside_brain = make_lab(os.path.join(runtime.settings.brain_vault, "lab"))
    reply = owner.post(f"{PREFIX}/lab", json={"folder": inside_brain})
    assert reply.status_code == 422 and "this app's own" in reply.text


def test_the_connected_lab_is_remembered_on_this_machine(owner, lab, runtime):
    before = owner.ok(owner.get(PREFIX))
    assert before["source"] == "builtin" and before["lab"] is None
    after = owner.ok(owner.post(f"{PREFIX}/lab", json={"folder": lab}))
    assert after["source"] == "lab" and after["lab"]["name"] == "Stub Lab"
    assert after["lab"]["contract"] == 1
    # Kept in this app's own data folder, not in the Lab and not in the Brain.
    saved = os.path.join(runtime.settings.data_dir, "test-the-brain", "settings.json")
    with open(saved, encoding="utf-8") as handle:
        assert json.load(handle)["lab_folder"] == os.path.realpath(lab)
    from workspace_server.brain_testing import TestTheBrain

    again = TestTheBrain(runtime.settings, runtime.ws)
    assert again.connected_folder() == os.path.realpath(lab)
    gone = owner.ok(owner.delete(f"{PREFIX}/lab"))
    assert gone["source"] == "builtin" and gone["lab"] is None
    assert os.path.exists(os.path.join(lab, "lab.contract.json")), (
        "disconnecting leaves the Lab alone"
    )


def test_a_lab_that_stops_working_says_so_instead_of_breaking_the_page(owner, connected):
    os.remove(os.path.join(connected, "lab.contract.json"))
    state = owner.ok(owner.get(PREFIX))
    assert state["source"] == "lab" and "lab.contract.json" in state["error"]


# ------------------------------------------------------------------ reading the results
def run_fast(owner):
    started = owner.ok(owner.post(f"{PREFIX}/runs", json={"kind": "fast"}), 202)
    live = wait_for(lambda: finished(owner))
    assert live["active"]["state"] == "done", live
    return started, live


def test_the_status_lists_the_run_kinds_gates_and_readiness(owner, connected):
    state = owner.ok(owner.get(PREFIX))
    status = state["status"]
    assert [k["id"] for k in status["run_kinds"]] == ["fast", "smoke", "slow", "crash"]
    assert any(k["paid"] for k in status["run_kinds"])
    assert {r["state"] for r in status["ready"]} >= {"ready", "waiting_step", "pc_only"}
    assert state["running"] is None


def test_a_run_streams_its_progress_and_its_results_can_be_read(owner, connected):
    started, live = run_fast(owner)
    run = started["run"]
    states = [e["event"] for e in live["events"]]
    assert states[0] == "start" and states[-1] == "end" and "failure" in states
    runs = owner.ok(owner.get(f"{PREFIX}/runs"))["runs"]
    assert [r["run"] for r in runs] == [run]
    summary = owner.ok(owner.get(f"{PREFIX}/runs/{run}"))
    assert summary["metrics"][0]["gate"] == "retrieval.needed_recall.heldout"
    cases = owner.ok(owner.get(f"{PREFIX}/runs/{run}/cases"))
    assert cases["total"] == 5 and set(cases["kinds"]) == {
        "retrieval",
        "outcome",
        "world",
        "session",
        "table",
    }
    assert cases["cases"][0]["pass"] is False, "failures come first"
    assert all("view" not in c for c in cases["cases"])
    only = owner.ok(owner.get(f"{PREFIX}/runs/{run}/cases", params={"kind": "outcome"}))
    assert [c["id"] for c in only["cases"]] == ["OC-demo-1"]
    one = owner.ok(owner.get(f"{PREFIX}/runs/{run}/cases/RT-demo-1"))
    assert one["view"]["notes"][1]["label"] == "needed_missed"
    assert one["request"] == "Write an invite for the autumn open day."


def test_progress_can_be_read_in_pieces(owner, connected):
    _started, live = run_fast(owner)
    first = owner.ok(owner.get(f"{PREFIX}/live", params={"after": 3}))
    assert [e["event"] for e in first["events"]] == [e["event"] for e in live["events"]][3:]
    assert first["next"] == live["next"]
    nothing = owner.ok(owner.get(f"{PREFIX}/live", params={"after": live["next"]}))
    assert nothing["events"] == []


def test_a_run_or_case_name_cannot_walk_out_of_the_results_folder(owner, connected):
    # (An HTTP client folds a bare ".." away before it is sent, so that one is checked below.)
    for bad in ("a..b", "x%2F..%2F..", "%2e%2e%2fsecret", "run%5C..%5Cx"):
        reply = owner.get(f"{PREFIX}/runs/{bad}")
        assert reply.status_code in (404, 422), (bad, reply.status_code)
    results = lab_contract.Results(os.path.join(connected, "results"))
    for bad in ("..", ".", "../x", "a/b", "a\\b", "", "x" * 300):
        with pytest.raises(ContractError):
            results.run_dir(bad)
    _started, _live = run_fast(owner)
    run = owner.ok(owner.get(f"{PREFIX}/runs"))["runs"][0]["run"]
    assert owner.get(f"{PREFIX}/runs/{run}/cases/..%2Fsummary").status_code in (404, 422)


def test_lines_that_do_not_fit_the_contract_are_skipped_and_counted(owner, connected):
    started, _live = run_fast(owner)
    path = os.path.join(connected, "results", "runs", started["run"], "cases.jsonl")
    with open(path, "a", encoding="utf-8") as handle:
        handle.write("not json\n[1, 2]\n" + json.dumps({"no_id": True}) + "\n")
    cases = owner.ok(owner.get(f"{PREFIX}/runs/{started['run']}/cases"))
    assert cases["total"] == 5 and cases["skipped"] == 3


def test_the_gates_join_the_bars_with_the_latest_values(owner, connected):
    run_fast(owner)
    gates = owner.ok(owner.get(f"{PREFIX}/gates"))["gates"]
    recall = next(g for g in gates if g["id"] == "retrieval.needed_recall.heldout")
    assert recall["value"] == 0.78 and recall["ci"] == [0.69, 0.86]
    assert recall["met"] is False and recall["bar"] == {"op": ">=", "value": 0.9}
    assert recall["kind"] == "hard" and recall["source"] == "BL 5.9"
    assert recall["pillar"] == "retrieval" and recall["trend"] == [0.78]
    quiet = next(g for g in gates if g["id"] == "retrieval.noise_share")
    assert quiet["met"] is True and quiet["met_confident"] is True
    idle = next(g for g in gates if g["id"] == "agent.precision")
    assert idle["value"] is None, "a gate no run has measured shows no value"


def test_two_runs_compare_by_the_gates_that_moved_and_the_cases_that_flipped(owner, connected):
    first, _ = run_fast(owner)
    second, _ = run_fast(owner)
    runs_dir = os.path.join(connected, "results", "runs")
    path = os.path.join(runs_dir, second["run"], "cases.jsonl")
    with open(path, encoding="utf-8") as handle:
        lines = [json.loads(line) for line in handle]
    for line in lines:
        if line["id"] == "RT-demo-1":
            line["pass"] = True
    with open(path, "w", encoding="utf-8") as handle:
        handle.writelines(json.dumps(line) + "\n" for line in lines)
    sum_path = os.path.join(runs_dir, second["run"], "summary.json")
    with open(sum_path, encoding="utf-8") as handle:
        summary = json.load(handle)
    summary["metrics"][0].update(value=0.93, met=True, met_confident=True)
    write_json(sum_path, summary)
    both = owner.ok(owner.get(f"{PREFIX}/compare", params={"a": first["run"], "b": second["run"]}))
    moved = {m["id"]: m for m in both["metrics"]}
    assert moved["retrieval.needed_recall:heldout"]["delta"] == pytest.approx(0.15)
    assert [(c["id"], c["from"], c["to"]) for c in both["flipped"]] == [("RT-demo-1", False, True)]


# ------------------------------------------------------------------ starting and cancelling
def test_only_the_run_kinds_the_lab_lists_can_start(owner, connected):
    assert owner.post(f"{PREFIX}/runs", json={"kind": "everything"}).status_code == 422
    assert owner.post(f"{PREFIX}/runs", json={"kind": "../fast"}).status_code == 422
    assert owner.post(f"{PREFIX}/runs", json={"kind": "fast", "suite": "x; rm"}).status_code == 422
    assert owner.get(f"{PREFIX}/runs").json()["runs"] == []


def test_a_paid_run_needs_a_second_press(owner, connected):
    first = owner.post(f"{PREFIX}/runs", json={"kind": "smoke"})
    assert first.status_code == 409
    asked = first.json()["error"]
    assert asked["needs_confirmation"] is True
    assert asked["estimate"] == {"usd": 4.5, "seconds": 900}
    assert owner.get(f"{PREFIX}/runs").json()["runs"] == []
    owner.ok(owner.post(f"{PREFIX}/runs", json={"kind": "smoke", "confirm": True}), 202)
    wait_for(lambda: finished(owner))


def test_a_suite_narrows_a_run(owner, connected):
    owner.ok(owner.post(f"{PREFIX}/runs", json={"kind": "fast", "suite": "outcomes"}), 202)
    live = wait_for(lambda: finished(owner))
    assert {e.get("suite") for e in live["events"] if e["event"] == "suite_start"} == {"outcomes"}


def test_one_run_at_a_time(owner, connected):
    started = owner.ok(owner.post(f"{PREFIX}/runs", json={"kind": "slow"}), 202)
    again = owner.post(f"{PREFIX}/runs", json={"kind": "fast"})
    assert again.status_code == 409 and "already running" in again.text
    owner.ok(owner.post(f"{PREFIX}/runs/{started['run']}/cancel"))
    wait_for(lambda: finished(owner))


def test_the_labs_run_lock_is_honored(owner, connected):
    owner.ok(owner.get(PREFIX))
    status_path = os.path.join(connected, "results", "status.json")
    run_fast(owner)  # the stub writes its status on its first run
    with open(status_path, encoding="utf-8") as handle:
        status = json.load(handle)
    status["lock"] = {"run": "2026-01-01T00-00_fast_A_other_000001"}
    write_json(status_path, status)
    held = owner.post(f"{PREFIX}/runs", json={"kind": "fast"})
    assert held.status_code == 409
    assert "2026-01-01T00-00_fast_A_other_000001" in held.text
    state = owner.ok(owner.get(PREFIX))
    assert state["status"]["lock_holder"] == "2026-01-01T00-00_fast_A_other_000001"


def test_a_runner_that_refuses_or_breaks_says_why(owner, connected):
    started = owner.post(f"{PREFIX}/runs", json={"kind": "crash"})
    if started.status_code == 202:
        live = wait_for(lambda: finished(owner))
        assert live["active"]["state"] == "failed"
        assert "broke on purpose" in live["active"]["message"]
    else:
        assert started.status_code == 409 and "broke on purpose" in started.text


def test_cancelling_stops_the_run_and_leaves_no_process_behind(owner, connected):
    started = owner.ok(owner.post(f"{PREFIX}/runs", json={"kind": "slow"}), 202)
    pids_path = os.path.join(connected, "results", "runs", started["run"], "pids.json")
    pids = wait_for(lambda: read_json(pids_path), what="pids")
    assert alive(pids["runner"]) and alive(pids["child"])
    owner.ok(owner.post(f"{PREFIX}/runs/{started['run']}/cancel"))
    live = wait_for(lambda: finished(owner))
    assert live["active"]["state"] == "cancelled"
    wait_for(lambda: not alive(pids["runner"]) and not alive(pids["child"]), what="cleanup")
    assert owner.ok(owner.get(PREFIX))["running"] is None


def test_stopping_the_server_stops_a_run_in_progress(owner, connected, runtime):
    started = owner.ok(owner.post(f"{PREFIX}/runs", json={"kind": "slow"}), 202)
    pids_path = os.path.join(connected, "results", "runs", started["run"], "pids.json")
    pids = wait_for(lambda: read_json(pids_path), what="pids")
    assert alive(pids["runner"])
    runtime.close()
    wait_for(lambda: not alive(pids["runner"]) and not alive(pids["child"]), what="cleanup")


# ------------------------------------------------------------------ safety
def test_the_runner_never_sees_the_apps_settings(owner, connected, monkeypatch):
    live_values = {
        "CONTXT_DATA_DIR": "C:/live/workspace-data",
        "CONTXT_DATABASE_URL": "postgresql://live",
        "CONTXT_OWNER_TOKEN": "wst_live-owner-key",
        "WORKSPACE_BRAIN_VAULT": "C:/live/vault",
        "WORKSPACE_DATA_DIR": "C:/live/workspace-data",
        "BRAIN_VAULT": "C:/live/vault",
        "ANTHROPIC_API_KEY": "sk-live",
    }
    for name, value in live_values.items():
        monkeypatch.setenv(name, value)
    run_fast(owner)
    run = owner.ok(owner.get(f"{PREFIX}/runs"))["runs"][0]["run"]
    seen = owner.ok(owner.get(f"{PREFIX}/runs/{run}/cases/TB-env"))["view"]["env_names"]
    upper = {name.upper() for name in seen}
    assert not [n for n in upper if n.startswith(("CONTXT_", "WORKSPACE_"))]
    for name in live_values:
        assert name.upper() not in upper, name
    assert "PATH" in upper, "the allowlist still carries what a program needs to start"
    assert {"LAB_CONFIG", "LAB_PYTHON"} <= upper, "the contract's own variables pass"
    table = owner.ok(owner.get(f"{PREFIX}/runs/{run}/cases/TB-env"))["view"]["rows"]
    assert next(r["got"] for r in table if r["label"] == "LAB_CONFIG") == "stub-config"


def test_the_runner_is_started_with_a_short_environment_and_no_shell(
    connected, runtime, monkeypatch
):
    from workspace_server import lab_runner

    monkeypatch.setenv("CONTXT_DATA_DIR", "x")
    monkeypatch.setenv("SOME_OTHER_THING", "y")
    contract = lab_contract.open_lab(connected).contract
    env = lab_runner.child_environment(contract)
    assert set(env) <= set(lab_runner.BASE_ENV) | set(contract.env_allow)
    assert "CONTXT_DATA_DIR" not in env and "SOME_OTHER_THING" not in env
    assert lab_runner.BASE_ENV == ("PATH", "SYSTEMROOT", "TEMP", "TMP", "USERPROFILE")


def test_only_the_owner_can_see_or_use_any_of_it(client, owner, model, connected):
    class Anonymous:
        def __getattr__(self, method):
            return lambda path, **kw: getattr(client, method)(path, **kw)

    anonymous = Anonymous()
    calls = [
        ("get", PREFIX),
        ("get", f"{PREFIX}/runs"),
        ("get", f"{PREFIX}/runs/x"),
        ("get", f"{PREFIX}/runs/x/cases"),
        ("get", f"{PREFIX}/live"),
        ("get", f"{PREFIX}/gates"),
        ("get", f"{PREFIX}/compare?a=x&b=y"),
        ("post", f"{PREFIX}/runs"),
        ("post", f"{PREFIX}/runs/x/cancel"),
        ("post", f"{PREFIX}/lab"),
        ("post", f"{PREFIX}/watch"),
        ("get", f"{PREFIX}/overview"),
        ("delete", f"{PREFIX}/lab"),
    ]
    for who, expected in ((anonymous, 401), (model, 403)):
        for method, path in calls:
            reply = getattr(who, method)(
                path, **({"json": {"kind": "fast", "folder": "x"}} if method == "post" else {})
            )
            assert reply.status_code == expected, (method, path, reply.status_code)


def test_the_page_writes_nothing_but_starting_and_cancelling_runs(
    client, owner, connected, runtime
):
    expected = {
        ("POST", f"{PREFIX}/runs"),
        ("POST", f"{PREFIX}/runs/{{run}}/cancel"),
        ("POST", f"{PREFIX}/lab"),
        ("DELETE", f"{PREFIX}/lab"),
        ("POST", f"{PREFIX}/watch"),  # read only: routes a request and records nothing
    }
    from workspace_server.routes import test_the_brain as page

    found = set()
    for route in page.router.routes:
        path = getattr(route, "path", "")
        if path.startswith(PREFIX):
            for method in getattr(route, "methods", None) or ():
                if method not in ("GET", "HEAD", "OPTIONS"):
                    found.add((method, path))
    assert found == expected, "approvals, gates and labels are never written from this page"
    # And reading everything changes nothing in the Lab or the Brain.
    run_fast(owner)
    run = owner.ok(owner.get(f"{PREFIX}/runs"))["runs"][0]["run"]
    lab_before = tree_listing(connected)
    brain_before = tree_listing(runtime.settings.brain_vault)
    for path in (
        PREFIX,
        f"{PREFIX}/runs",
        f"{PREFIX}/runs/{run}",
        f"{PREFIX}/runs/{run}/cases",
        f"{PREFIX}/runs/{run}/cases/RT-demo-1",
        f"{PREFIX}/gates",
        f"{PREFIX}/live",
    ):
        owner.ok(owner.get(path))
    assert tree_listing(connected) == lab_before
    assert tree_listing(runtime.settings.brain_vault) == brain_before


# ------------------------------------------------------------------ the overview
def test_the_overview_rolls_the_gates_up_by_pillar(owner, connected):
    empty = owner.ok(owner.get(f"{PREFIX}/overview"))
    assert [p["id"] for p in empty["pillars"]] == ["retrieval", "briefs", "management", "agent"]
    assert all(p["measured"] == 0 for p in empty["pillars"]), "nothing is measured before a run"
    run_fast(owner)
    found = owner.ok(owner.get(f"{PREFIX}/overview"))
    retrieval, briefs, _management, agent = found["pillars"]
    assert (retrieval["total"], retrieval["measured"], retrieval["met"]) == (2, 2, 1)
    assert retrieval["confident"] == 1
    assert retrieval["headline"]["value"] == 0.78 and retrieval["headline"]["ci"] == [0.69, 0.86]
    assert (briefs["total"], briefs["met"]) == (1, 1)
    assert (agent["total"], agent["measured"]) == (1, 0)
    assert found["effect"]["value"] == 0.21 and found["effect"]["ci"] == [0.05, 0.36]
    assert {r["state"] for r in found["ready"]} >= {"ready", "waiting_step", "pc_only"}
    assert found["labels"]["sitting"]["state"] == "ready"
    assert found["last"]["kind"] == "fast"


def test_a_labs_saved_case_is_drawn_from_its_own_record_and_nothing_is_rerun(owner, connected):
    started, _live = run_fast(owner)
    drawn = owner.ok(
        owner.post(f"{PREFIX}/watch", json={"run": started["run"], "case": "RT-demo-1"})
    )
    assert drawn["from_record"] is True and drawn["test"] is True and drawn["read_only"] is True
    fit = next(s for s in drawn["stages"] if s["id"] == "fit")
    assert [d["title"] for d in fit["dropped"]] == ["Open day dates"]
    assert drawn["request"] == "Write an invite for the autumn open day."


def test_a_gate_opens_the_cases_behind_it_worst_first(owner, connected):
    started, _live = run_fast(owner)
    behind = owner.ok(
        owner.get(
            f"{PREFIX}/runs/{started['run']}/cases",
            params={"gate": "retrieval.needed_recall.heldout"},
        )
    )
    assert [c["id"] for c in behind["cases"]] == ["RT-demo-1"], "the suite is the gate's first word"
    none = owner.ok(
        owner.get(f"{PREFIX}/runs/{started['run']}/cases", params={"gate": "agent.precision"})
    )
    assert none["total"] == 0
    named = os.path.join(connected, "results", "runs", started["run"], "cases.jsonl")
    with open(named, encoding="utf-8") as handle:
        lines = [json.loads(line) for line in handle]
    for line in lines:
        if line["id"] == "OC-demo-1":
            line["gates"] = ["agent.precision"]
    with open(named, "w", encoding="utf-8") as handle:
        handle.writelines(json.dumps(line) + "\n" for line in lines)
    again = owner.ok(
        owner.get(f"{PREFIX}/runs/{started['run']}/cases", params={"gate": "agent.precision"})
    )
    assert [c["id"] for c in again["cases"]] == ["OC-demo-1"], "a case that names its gates wins"


def test_a_lab_that_breaks_after_it_was_connected_does_not_break_the_live_view(owner, connected):
    os.remove(os.path.join(connected, "lab.contract.json"))
    live = owner.ok(owner.get(f"{PREFIX}/live"))
    assert live["active"] is None and live["events"] == []
    for path in (f"{PREFIX}/runs", f"{PREFIX}/gates", f"{PREFIX}/overview"):
        assert owner.get(path).status_code in (200, 422), path


def test_a_run_started_outside_this_page_is_followed_through_the_labs_progress_file(
    owner, connected
):
    started, _live = run_fast(owner)
    status_path = os.path.join(connected, "results", "status.json")
    with open(status_path, encoding="utf-8") as handle:
        status = json.load(handle)
    status["lock"] = {"run": started["run"]}  # as if the Lab's own pane had started it
    write_json(status_path, status)
    live = owner.ok(owner.get(f"{PREFIX}/live"))
    assert live["active"]["ours"] is False and live["active"]["run"] == started["run"]
    assert live["events"][0]["event"] == "start"
