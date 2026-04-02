# Codex Guidance

This repository is Claude-first. The only Codex workflow currently supported here is the bounded phase-1 preparation run launched by the admin panel.

When running the Codex phase-1 workflow:

- stay read-only
- use the `workspace` MCP server for all persisted state
- use subagents for assessment, research, and proving
- stop at phase `1.4`
- do not start planning or implementation

The phase-1 parent prompt lives at `.codex/prompts/phase1.md`. The intended subagent role cards live under `.codex/agents/`.
