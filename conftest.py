"""A test run leaves nothing behind in the temp folder.

Many tests make scratch Brains, ledgers and copies of the demo Brains with `tempfile`; some
outlive the test that made them, and on Windows a scratch Brain's git objects are read-only, so
removing it with errors ignored quietly keeps them. Every one goes in a folder made for this run,
removed when the run ends, read-only files included.
"""
import os
import shutil
import stat
import tempfile

import pytest


def _writable_then_again(func, path, _error):
    """A read-only file (a git object on Windows): make it writable, then remove it."""
    os.chmod(path, stat.S_IWRITE)
    func(path)


@pytest.fixture(scope="session", autouse=True)
def one_temp_folder_per_run():
    folder = tempfile.mkdtemp(prefix="contxt-tests-")
    before = tempfile.tempdir
    tempfile.tempdir = folder
    yield
    tempfile.tempdir = before
    try:
        shutil.rmtree(folder, onexc=_writable_then_again)
    except OSError:
        shutil.rmtree(folder, ignore_errors=True)  # a file still open: leave what is left
