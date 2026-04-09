# Research Principles

## Core Principles
Verify: Always examine actual evidence (code, commits, pages, DOM).
Thorough: Follow every lead, cross-check, dig until complete understanding.
Context: Understand bigger picture, not isolated facts.

## Research Tools
| Tool | Purpose |
|------|---------|
| Grep | Pattern search (keywords, annotations) |
| Glob | Find files (**/*.java, **/test/*.py) |
| Read | Examine file contents |
| LS | Directory structure |

## Code Research Strategy
1. Entry points > execution path > data flow
2. Search variations: classes, methods, interfaces, annotations, imports
3. Check tests for behavior, configs for setup

## Reporting
Include:
- Exact references (file:line)
- Context and connections
- Patterns identified
- Limitations of findings
