"""The results contract Test the Brain reads (testing-lab plan C.5), and a reader for it.

Any runner that keeps the contract works with the page, so the app depends on the contract and
never on one test suite. A runner is described by `lab.contract.json` at the root of its folder:

    {"contract": 1, "name": "...", "results": "results",
     "runner": {"exe": "bin/lab", "cwd": ".", "args": []}, "env_allow": ["LAB_CONFIG"]}

and writes, in its results folder: `status.json`, and for each run `runs/<run>/summary.json`,
`cases.jsonl` and `progress.jsonl`. Everything here only reads those files. Nothing in the app
writes into a runner's folder; the only writes the page causes are starting and cancelling a run
(`lab_runner.py`).

Every file is untrusted input from another program: a line that does not fit is skipped and
counted, a name that would leave the results folder is refused, and a contract version this app
does not know is refused with a message, never guessed at.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

CONTRACT_FILE = "lab.contract.json"
SUPPORTED_CONTRACTS = (1,)
MAX_JSON_BYTES = 8 * 1024 * 1024
MAX_LINE_BYTES = 2 * 1024 * 1024
ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:\-]{0,119}$")
ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
# What a runner may never be handed, however its contract asks: the app's own settings
# (tests run with the live storage settings loaded write to the live store).
FORBIDDEN_ENV_PREFIXES = ("CONTXT_", "WORKSPACE_")
CASE_KINDS = ("retrieval", "outcome", "world", "session", "table")


class ContractError(ValueError):
    """The folder, its contract or a results file is not usable; the message says what to do."""


class MissingResult(ContractError):
    """A run or case that is not there (the page answers 404, not 422)."""


def _model() -> ConfigDict:
    return ConfigDict(extra="allow")


def _first_error(exc: ValidationError) -> str:
    first = exc.errors()[0]
    where = ".".join(str(part) for part in first["loc"])
    return f"{where}: {first['msg']}"


# --------------------------------------------------------------------------- the contract
class RunnerSpec(BaseModel):
    model_config = _model()
    exe: str
    cwd: str = "."
    args: list[str] = Field(default_factory=list)


class Contract(BaseModel):
    model_config = _model()
    contract: int
    name: str = "Test lab"
    results: str = "results"
    runner: RunnerSpec
    env_allow: list[str] = Field(default_factory=list)


def read_json(path: str, *, what: str) -> Any:
    try:
        if os.path.getsize(path) > MAX_JSON_BYTES:
            raise ContractError(f"{what} is larger than {MAX_JSON_BYTES // 1024 // 1024} MB.")
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        raise ContractError(f"{what} is not there yet ({os.path.basename(path)}).") from None
    except (OSError, ValueError) as exc:
        raise ContractError(f"{what} could not be read: {exc}") from None


def inside(root: str, candidate: str) -> bool:
    """True when `candidate` (symlinks resolved) is `root` or below it."""
    top = os.path.realpath(root)
    path = os.path.realpath(candidate)
    try:
        return os.path.commonpath([top, path]) == top
    except ValueError:  # another drive
        return False


def resolve_inside(root: str, relative: str, *, what: str) -> str:
    """A path the contract names, resolved from `root`, and refused when it is absolute or
    would land outside `root` (a `..`, a drive, a link out)."""
    text = str(relative or "").strip()
    if not text:
        raise ContractError(f"The contract's {what} is empty.")
    if os.path.isabs(text) or text.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", text):
        raise ContractError(
            f"The contract's {what} must be a path inside the Lab's folder, not an absolute one."
        )
    path = os.path.normpath(os.path.join(root, text))
    if not inside(root, path):
        raise ContractError(f"The contract's {what} leaves the Lab's folder, so it is refused.")
    return path


def parse_contract(data: Any) -> Contract:
    """The contract in `data`, or a ContractError saying what to change."""
    if not isinstance(data, dict):
        raise ContractError("lab.contract.json must hold one JSON object.")
    version = data.get("contract")
    if isinstance(version, bool) or not isinstance(version, int):
        raise ContractError("lab.contract.json has no `contract` version number.")
    if version not in SUPPORTED_CONTRACTS:
        known = ", ".join(str(v) for v in SUPPORTED_CONTRACTS)
        raise ContractError(
            f"This Lab speaks results contract {version}, which this version of Contxt does "
            f"not know (it reads {known}). Update Contxt, or ask the Lab for a contract it can "
            "read. Nothing was guessed."
        )
    try:
        contract = Contract.model_validate(data)
    except ValidationError as exc:
        raise ContractError(f"lab.contract.json: {_first_error(exc)}.") from None
    for name in contract.env_allow:
        if not ENV_NAME.match(name):
            raise ContractError(f"env_allow names {name!r}, which is not a variable name.")
        if name.upper().startswith(FORBIDDEN_ENV_PREFIXES):
            raise ContractError(
                f"env_allow names {name}, which holds this app's own settings. A Lab never "
                "receives those."
            )
    return contract


@dataclass(frozen=True)
class Lab:
    """A contract that passed every check, with the three places it names, resolved."""

    folder: str
    contract: Contract
    exe: str
    cwd: str
    results: str

    @property
    def name(self) -> str:
        return self.contract.name


def open_lab(folder: str) -> Lab:
    """Read and check the contract in `folder`. Run again before every use: the Lab's files
    can change after the owner connected it."""
    if not folder or not os.path.isdir(folder):
        raise ContractError("That folder is not there. Pick the Lab's folder.")
    root = os.path.realpath(folder)
    path = os.path.join(root, CONTRACT_FILE)
    if not os.path.isfile(path):
        raise ContractError(
            f"There is no {CONTRACT_FILE} in that folder. Pick the folder the Lab keeps it in."
        )
    contract = parse_contract(read_json(path, what="The Lab's contract"))
    exe = resolve_inside(root, contract.runner.exe, what="runner.exe")
    cwd = resolve_inside(root, contract.runner.cwd or ".", what="runner.cwd")
    results = resolve_inside(root, contract.results, what="results folder")
    if not os.path.isfile(exe):
        raise ContractError(
            f"The Lab's runner ({contract.runner.exe}) is not there. Set the Lab up first."
        )
    if not os.path.isdir(cwd):
        raise ContractError(f"The Lab's runner folder ({contract.runner.cwd}) is not there.")
    return Lab(root, contract, exe, cwd, results)


# --------------------------------------------------------------------------- status.json
class Cost(BaseModel):
    model_config = _model()
    usd_estimate: float | None = None
    tokens: int | None = None
    seconds: float | None = None


class RunKind(BaseModel):
    """A run the page may start: only the kinds the contract's status lists."""

    model_config = _model()
    id: str
    name: str = ""
    covers: str = ""
    paid: bool = False
    last: dict[str, Any] | None = None  # {"run", "at", "seconds", "usd"}
    estimate: dict[str, Any] | None = None  # {"usd", "seconds"}
    suites: list[str] = Field(default_factory=list)


class GateSpec(BaseModel):
    model_config = _model()
    id: str
    name: str = ""
    bar: Any = None  # {"op": ">=", "value": 0.9}
    kind: Literal["hard", "watch"] = "hard"
    source: str = ""
    pillar: str | None = None


class Status(BaseModel):
    model_config = _model()
    updated: str | None = None
    engine_ref: str | None = None
    machine_setup: str | None = None
    brain: str | None = None  # the Brain under test: the Lab's, never the live one
    run_kinds: list[RunKind] = Field(default_factory=list)
    ready: list[dict[str, Any]] = Field(default_factory=list)
    gates: list[GateSpec] = Field(default_factory=list)
    labels: dict[str, Any] = Field(default_factory=dict)
    qualification: list[dict[str, Any]] = Field(default_factory=list)
    lock: Any = None  # null when free, else {"run": id} or the run id

    def lock_holder(self) -> str | None:
        if not self.lock:
            return None
        if isinstance(self.lock, str):
            return self.lock
        if isinstance(self.lock, dict):
            return str(self.lock.get("run") or "held")
        return "held"

    def kind(self, kind_id: str) -> RunKind | None:
        return next((k for k in self.run_kinds if k.id == kind_id), None)


# --------------------------------------------------------------------------- runs
class Metric(BaseModel):
    model_config = _model()
    id: str
    split: str | None = None
    n: int | None = None
    value: float | None = None
    ci: list[float] | None = None
    gate: str | None = None
    met: bool | None = None
    met_confident: bool | None = None
    pillar: str | None = None


class FailingCase(BaseModel):
    model_config = _model()
    id: str
    title: str = ""
    why: str = ""


class Summary(BaseModel):
    model_config = _model()
    run: str
    kind: str = ""
    config: dict[str, Any] = Field(default_factory=dict)
    valid: bool = True
    metrics: list[Metric] = Field(default_factory=list)
    cost: Cost = Field(default_factory=Cost)
    failing_cases: list[FailingCase] = Field(default_factory=list)
    started: str | None = None
    ended: str | None = None
    note: str | None = None


class Case(BaseModel):
    """One line of cases.jsonl. `view` is what the Cases tab draws for the case's kind."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)
    id: str
    suite: str = ""
    kind: str = "table"
    title: str = ""
    sensitive: bool = False
    passed: bool | None = Field(default=None, alias="pass")
    measures: dict[str, Any] = Field(default_factory=dict)
    request: str | None = None
    view: dict[str, Any] = Field(default_factory=dict)

    def behind(self, gate: str) -> bool:
        """Whether this case is one behind a gate: it names the gate in `gates`, or, when it
        names none, its suite is the gate's first word (retrieval.noise_share: retrieval)."""
        named = (self.model_extra or {}).get("gates")
        if isinstance(named, list):
            return gate in named
        return bool(self.suite) and self.suite == gate.split(".", 1)[0]

    def listing(self) -> dict[str, Any]:
        """The row the Cases list shows: everything but the view."""
        return {
            "id": self.id,
            "suite": self.suite,
            "kind": self.kind if self.kind in CASE_KINDS else "table",
            "title": self.title,
            "sensitive": self.sensitive,
            "pass": self.passed,
            "measures": self.measures,
        }

    def full(self) -> dict[str, Any]:
        text = self.request or self.view.get("request")
        return dict(self.listing(), request=text, view=self.view)


class ProgressEvent(BaseModel):
    model_config = _model()
    event: str
    at: str | None = None
    run: str | None = None
    suite: str | None = None
    case: str | None = None
    done: int | None = None
    total: int | None = None
    failures: int | None = None
    message: str | None = None


# --------------------------------------------------------------------------- the reader
def check_id(value: str, *, what: str) -> str:
    text = str(value or "")
    if not ID_PATTERN.match(text) or ".." in text:
        raise ContractError(f"{what} {text[:40]!r} is not a name this page opens.")
    return text


class Results:
    """The files in one results folder, read. Never writes."""

    def __init__(self, root: str) -> None:
        self.root = os.path.realpath(root)
        self.skipped = 0

    # ----- paths
    def run_dir(self, run: str) -> str:
        name = check_id(run, what="The run")
        path = os.path.join(self.root, "runs", name)
        if not inside(self.root, path):
            raise ContractError("That run's folder leaves the results folder, so it is refused.")
        return path

    # ----- status
    def status(self) -> Status | None:
        path = os.path.join(self.root, "status.json")
        if not os.path.isfile(path):
            return None
        try:
            return Status.model_validate(read_json(path, what="The Lab's status"))
        except ValidationError as exc:
            raise ContractError(f"status.json: {_first_error(exc)}.") from None

    # ----- runs
    def run_ids(self) -> list[str]:
        folder = os.path.join(self.root, "runs")
        if not os.path.isdir(folder):
            return []
        names = [
            n
            for n in os.listdir(folder)
            if ID_PATTERN.match(n) and os.path.isfile(os.path.join(folder, n, "summary.json"))
        ]
        return sorted(names, reverse=True)

    def summary(self, run: str) -> Summary:
        path = os.path.join(self.run_dir(run), "summary.json")
        if not os.path.isfile(path):
            raise MissingResult(f"There is no run {run}.")
        try:
            return Summary.model_validate(read_json(path, what=f"Run {run}'s summary"))
        except ValidationError as exc:
            raise ContractError(f"Run {run}'s summary: {_first_error(exc)}.") from None

    def summaries(self, *, kind: str | None = None, limit: int = 200) -> list[Summary]:
        """Newest first. A run whose summary cannot be read is left out, not fatal."""
        out: list[Summary] = []
        for run in self.run_ids():
            try:
                found = self.summary(run)
            except ContractError:
                continue
            if kind and found.kind != kind:
                continue
            out.append(found)
            if len(out) >= limit:
                break
        return out

    # ----- cases
    def _lines(self, path: str) -> Iterator[dict[str, Any]]:
        """Each JSON object of a .jsonl file. A bad or oversize line is skipped and counted
        in `self.skipped`."""
        self.skipped = 0
        if not os.path.isfile(path):
            return
        with open(path, "rb") as handle:
            for raw in handle:
                if len(raw) > MAX_LINE_BYTES:
                    self.skipped += 1
                    continue
                text = raw.strip()
                if not text:
                    continue
                try:
                    item = json.loads(text)
                except ValueError:
                    self.skipped += 1
                    continue
                if isinstance(item, dict):
                    yield item
                else:
                    self.skipped += 1

    def cases(
        self,
        run: str,
        *,
        kind: str | None = None,
        suite: str | None = None,
        passed: bool | None = None,
        gate: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        """A page of the run's cases, failures first, without their views."""
        path = os.path.join(self.run_dir(run), "cases.jsonl")
        rows: list[Case] = []
        skipped = 0
        for item in self._lines(path):
            try:
                case = Case.model_validate(item)
            except ValidationError:
                skipped += 1
                continue
            if kind and case.kind != kind:
                continue
            if suite and case.suite != suite:
                continue
            if passed is not None and case.passed is not passed:
                continue
            if gate and not case.behind(gate):
                continue
            rows.append(case)
        skipped += self.skipped
        rows.sort(key=lambda c: (c.passed is True, c.id))  # failures, then unknown, then passes
        start = max(0, offset)
        page = rows[start : start + max(1, min(limit, 500))]
        return {
            "total": len(rows),
            "skipped": skipped,
            "kinds": sorted({c.kind for c in rows}),
            "cases": [c.listing() for c in page],
        }

    def case(self, run: str, case_id: str) -> Case:
        wanted = check_id(case_id, what="The case")
        for item in self._lines(os.path.join(self.run_dir(run), "cases.jsonl")):
            if item.get("id") == wanted:
                try:
                    return Case.model_validate(item)
                except ValidationError:
                    raise ContractError(f"Case {wanted} does not fit the contract.") from None
        raise MissingResult(f"Run {run} has no case {wanted}.")

    # ----- progress
    @staticmethod
    def progress(path: str, after: int = 0, limit: int = 500) -> dict[str, Any]:
        """The events of a progress file past line `after`: {"events", "next"}, `next` being
        the line count to pass back. Only whole lines are read, so a line still being written
        waits for the next call."""
        events: list[dict[str, Any]] = []
        line = 0
        if not os.path.isfile(path):
            return {"events": events, "next": after}
        with open(path, "rb") as handle:
            for raw in handle:
                if not raw.endswith(b"\n"):
                    break
                if line >= after + limit:
                    break
                line += 1
                if line <= after:
                    continue
                if len(raw) > MAX_LINE_BYTES:
                    continue
                try:
                    events.append(
                        ProgressEvent.model_validate(json.loads(raw)).model_dump(exclude_none=True)
                    )
                except (ValueError, ValidationError):
                    continue
        return {"events": events, "next": max(after, line)}
