def test_a_connector_check_line_says_each_step_and_counts_only():
    from workspace_server.cli import connector_line

    ok = {
        "passed": True,
        "steps": [
            {"step": "found", "ok": True, "line": "Found in your Claude account."},
            {"step": "signed in", "ok": True, "line": "Signed in."},
            {"step": "read-only", "ok": True, "line": "11 tools only read; 0 refused."},
            {
                "step": "test read",
                "ok": True,
                "items": 10,
                "returned": 10,
                "tokens": 69170,
                "seconds": 44.0,
                "cost": 0.05,
                "per_day": 1.2,
            },
        ],
    }
    line = connector_line("Google Drive", ok)
    assert line.startswith("Google Drive: ready for heartbeats.")
    assert "10 items, 10 returned, 69170 tokens, 44.0 s, $0.050 a read, at most $1.20 a day" in line
    failed = {
        "passed": False,
        "steps": [
            {"step": "found", "ok": True, "line": ""},
            {"step": "signed in", "ok": False, "line": "Sign in again in claude.ai."},
        ],
    }
    assert "signed in FAILED (Sign in again in claude.ai.)" in connector_line("Gmail", failed)
