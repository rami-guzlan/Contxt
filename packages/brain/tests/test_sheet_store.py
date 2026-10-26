"""Context sheets in SQLite (the owner's list, item 3): a sheet's cell events live in one
SQLite file inside the Brain folder (`state/sheets.sqlite`), the same append-only events
behind the same API. The database is a working store, kept out of git and rebuilt from the
events when it is missing or behind; git keeps the events as append-only text, one file a
month (`state/events/<YYYY-MM>.jsonl`), with each sheet's SNAPSHOT.md, committed once per beat
or once a day, not on every write. Earlier per-row `.jsonl` logs are imported once."""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import unittest
from unittest import mock

from brainkit import sheetstore, state, util, versions
from brainkit.api import Brain
from tests import fixture

NOW = dt.datetime(2026, 10, 10, 12, 0, tzinfo=dt.timezone.utc)


def _git(base, *args):
    return subprocess.run(["git", *args], cwd=base, check=True, capture_output=True,
                          text=True).stdout


def _dirty(base) -> list[str]:
    """The sheet files with changes git does not have."""
    lines = _git(base, "status", "--porcelain", "--untracked-files=all").splitlines()
    return [line[3:] for line in lines if "/state/" in "/" + line[3:]]


class SheetStoreTest(unittest.TestCase):
    def setUp(self):
        self.clock = mock.patch.object(util, "now", return_value=NOW)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.vault = fixture.build(git=True)
        self.base = os.path.dirname(self.vault)
        self.brain = Brain(self.vault, embeddings=False)
        made = self.brain.state_act("create_sheet", {"template": "accounts"})
        self.assertFalse(made.is_error, made.text)
        self.folder = os.path.join(self.vault, "state", "accounts")

    def tearDown(self):
        self.brain.close()
        fixture.remove(self.vault)

    def write(self, row, values):
        done = self.brain.state_act("write", {"sheet": "accounts", "row": row, "values": values})
        self.assertFalse(done.is_error, done.text)

    def add(self, key, **values):
        done = self.brain.state_act("add_row", {"sheet": "accounts", "key": key,
                                                "values": values})
        self.assertFalse(done.is_error, done.text)

    def test_cell_events_go_to_the_sqlite_file_not_to_jsonl(self):
        self.add("Northwind", Health="green")
        self.write("Northwind", {"Health": "amber"})
        path = os.path.join(self.vault, "state", sheetstore.FILE)
        self.assertTrue(os.path.isfile(path))
        self.assertEqual([n for n in os.listdir(self.folder) if n.endswith(".jsonl")], [])
        row = state.find_row(self.brain, "accounts", "Northwind")
        self.assertEqual(row.value("Health"), "amber")
        history = state.history(self.brain, "accounts", "Northwind", "Health")
        self.assertEqual([e["value"] for e in history], ["amber", "green"])
        with open(os.path.join(self.folder, "SNAPSHOT.md"), encoding="utf-8") as handle:
            self.assertIn("| Northwind |", handle.read())

    def test_a_write_is_not_committed_until_the_beat_or_the_day_is_done(self):
        self.add("Northwind", Health="green")
        _git(self.base, "add", "-A")
        _git(self.base, "-c", "user.name=T", "-c", "user.email=t@example.com",
             "commit", "-q", "-m", "start")
        self.write("Northwind", {"Health": "amber"})
        dirty = _dirty(self.base)
        self.assertTrue(any("SNAPSHOT.md" in p for p in dirty), dirty)
        # A note written meanwhile does not carry the sheets with it.
        self.brain.remember("Northwind renews in the spring.")
        self.assertTrue(any("SNAPSHOT.md" in p for p in _dirty(self.base)))
        committed = self.brain.commit_sheets("the beat is done")
        self.assertTrue(committed["committed"], committed)
        self.assertEqual(_dirty(self.base), [])
        # The next day's first write commits the day's sheets by itself.
        self.write("Northwind", {"Health": "red"})
        self.assertTrue(_dirty(self.base))
        later = NOW + dt.timedelta(days=1, minutes=5)
        with mock.patch.object(util, "now", return_value=later):
            self.write("Northwind", {"Health": "green"})
        self.assertEqual(_dirty(self.base), [])

    def test_git_keeps_the_events_as_monthly_text_and_never_the_database(self):
        self.add("Northwind", Health="green")
        self.write("Northwind", {"Health": "amber"})
        self.brain.commit_sheets("the beat is done")
        tracked = _git(self.base, "ls-files").splitlines()
        self.assertIn("vault/state/events/2026-10.jsonl", tracked)
        self.assertFalse(any(p.endswith(".sqlite") for p in tracked), tracked)
        with open(os.path.join(self.vault, "state", "events", "2026-10.jsonl"),
                  encoding="utf-8") as handle:
            lines = [json.loads(line) for line in handle if line.strip()]
        self.assertEqual([e["event"].get("value") for e in lines
                          if e["event"].get("kind") == "cell"][-1], "amber")
        before = len(lines)
        self.write("Northwind", {"Health": "red"})
        self.brain.commit_sheets("the next beat")
        with open(os.path.join(self.vault, "state", "events", "2026-10.jsonl"),
                  encoding="utf-8") as handle:
            after = [json.loads(line) for line in handle if line.strip()]
        self.assertEqual(after[:before], lines)  # appended, never rewritten
        self.assertEqual(len(after), before + 1)

    def test_a_missing_or_stale_database_is_rebuilt_from_the_events(self):
        self.add("Northwind", Health="green")
        self.write("Northwind", {"Health": "amber"})
        self.brain.commit_sheets("beat one")
        db = os.path.join(self.vault, "state", sheetstore.FILE)
        with open(db, "rb") as handle:
            older = handle.read()
        self.write("Northwind", {"Health": "red"})
        self.brain.commit_sheets("beat two")
        self.brain.close()
        os.remove(db)  # missing: rebuilt
        self.brain = Brain(self.vault, embeddings=False)
        history = state.history(self.brain, "accounts", "Northwind", "Health")
        self.assertEqual([e["value"] for e in history], ["red", "amber", "green"])
        self.brain.close()
        with open(db, "wb") as handle:  # behind the newest event: caught up
            handle.write(older)
        self.brain = Brain(self.vault, embeddings=False)
        self.assertEqual(state.find_row(self.brain, "accounts", "Northwind").value("Health"),
                         "red")
        self.assertEqual(len(state.history(self.brain, "accounts", "Northwind", "Health")), 3)

    def test_earlier_jsonl_cell_logs_are_imported_once(self):
        self.brain.close()
        legacy = os.path.join(self.folder, "fabrikam.jsonl")
        events = [
            {"id": "e1", "kind": "row", "key": "Fabrikam", "at": NOW.isoformat(), "by": "owner"},
            {"id": "e2", "kind": "cell", "column": "Health", "value": "green",
             "at": NOW.isoformat(), "by": "owner"},
        ]
        with open(legacy, "w", encoding="utf-8") as handle:
            handle.write("".join(json.dumps(e) + "\n" for e in events))
        self.brain = Brain(self.vault, embeddings=False)
        row = state.find_row(self.brain, "accounts", "Fabrikam")
        self.assertIsNotNone(row)
        self.assertEqual(row.value("Health"), "green")
        self.assertFalse(os.path.exists(legacy))
        self.brain.close()
        self.brain = Brain(self.vault, embeddings=False)
        self.assertEqual(len(state.history(self.brain, "accounts", "Fabrikam")), 2)

    def test_a_version_diff_lists_the_cells_written_between_versions(self):
        self.add("Northwind", Health="green")
        self.assertFalse(versions.tag(self.brain, cause="manual").is_error)
        self.write("Northwind", {"Health": "amber"})
        self.assertFalse(versions.tag(self.brain, cause="manual").is_error)
        found = versions.diff(self.brain, "v1", "v2")
        self.assertEqual([(c["sheet"], c["column"], c["value"]) for c in found["cells"]],
                         [("accounts", "Health", "amber")])


if __name__ == "__main__":
    unittest.main()
