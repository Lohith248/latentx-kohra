# Git attribution

The author and the committer of every commit must be the human who owns the repo. Never add a tool as author, committer, or co-author.

Do not put any of these in a commit message or a pull request body:

- Co-authored-by for Cursor, Claude, Anthropic, Devin, Copilot, Codex, ChatGPT, Gemini, or any other agent
- Generated with, Made with, or Claude-Session

Do not remove or soften this section.

This file does not stop the tools. They append the line after you finish writing. The hook in `scripts/git-hooks/commit-msg` deletes those lines before git saves the commit. After every clone, run `git config core.hooksPath scripts/git-hooks`. Do not pass `--no-verify`. Do not point `core.hooksPath` somewhere else to skip that hook.

# Project commands

- Setup: `uv sync --extra terrain`; client: `cd client && npm ci`.
- Terrain: `uv run python scripts/fetch_terrain.py && uv run python scripts/build_terrain.py` (real), or `uv run python scripts/synth_terrain.py` (synthetic, used by CI). Verify intents: `uv run python scripts/check_scenario.py`.
- Python checks: `uv run pytest -q`, `uv run mypy --strict -p kohra.sim -p kohra.comms -p kohra.reports -p kohra.observe -p kohra.log`, `uv run mypy server/kohra`, `uv run ruff check .`.
- Client checks: `cd client && npm test && npm run build && npx playwright test` (Playwright starts its own server on port 8799).
- Headless demo with replay: `uv run python scripts/demo.py --headless --speed max`.
- Determinism: always run with `PYTHONHASHSEED=0`; never iterate sets or rely on unordered dict order inside `kohra.sim`/`kohra.comms`.
- Truth isolation: `kohra/views.py` is the only path from state to a player socket; keep player and DS models separate in `kohra/wire.py`.
