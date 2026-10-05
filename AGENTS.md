# Git attribution

The author and the committer of every commit must be the human who owns the repo. Never add a tool as author, committer, or co-author.

Do not put any of these in a commit message or a pull request body:

- Co-authored-by for Cursor, Claude, Anthropic, Devin, Copilot, Codex, ChatGPT, Gemini, or any other agent
- Generated with, Made with, or Claude-Session

Do not remove or soften this section.

This file does not stop the tools. They append the line after you finish writing. The hook in `scripts/git-hooks/commit-msg` deletes those lines before git saves the commit. After every clone, run `git config core.hooksPath scripts/git-hooks`. Do not pass `--no-verify`. Do not point `core.hooksPath` somewhere else to skip that hook.
