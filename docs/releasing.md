# Releasing

A release is a version tag. Pushing it runs CI (including the install check on Windows,
macOS and Linux) and the Release workflow, which builds the web app and publishes it with its
checksum, so `uv run contxt web --download` can fetch it.

1. Set the version in `packages/core/src/workspace_core/__init__.py` (`__version__`; the
   Release workflow refuses a tag that does not match it), in the `pyproject.toml` of the
   root, `apps/server`, `packages/core` and `packages/connectors`, and in
   `apps/web/package.json`. The Brain engine (`packages/brain`) keeps its own version.
2. In `CHANGELOG.md`, turn "unreleased" into the version and date.
3. Refresh the third-party notices: `uv run python scripts/third_party_notices.py`, and read
   its "For review" list.
4. `uv lock`, then `npm install --package-lock-only`.
5. Commit, then tag and push: `git tag v0.1.0`, `git push origin main v0.1.0`.
6. Once the Release workflow is done, try it from a fresh clone: `uv sync`,
   `uv run contxt web --download`, `uv run contxt setup`, `uv run contxt check`.

While the repository is private, `web --download` needs `GITHUB_TOKEN` set to a token that
can read it.
