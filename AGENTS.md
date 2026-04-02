# Codex Guidance

This repository is Claude-first. The Codex workflows currently supported here are the bounded phase-1 preparation run and the bounded phase-4 agentic review run launched by the admin panel.

When running the Codex phase-1 workflow:

- stay read-only
- use the `workspace` MCP server for all persisted state
- use subagents for assessment, research, and proving
- stop at phase `1.4`
- do not start planning or implementation

When running the Codex review workflow:

- stay read-only
- use the `workspace` MCP server for all persisted findings
- use reviewer subagents; do not review the whole codebase directly in the parent agent
- run only during phase `4.0`
- do not edit files or advance the phase yourself

The Codex parent prompts live under `.codex/prompts/`. The intended subagent role cards live under `.codex/agents/`.
