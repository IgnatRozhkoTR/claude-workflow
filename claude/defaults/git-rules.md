# Git Rules

## Commit Messages
- Format: `#<branch-name> <5-10 word description>`
- Example: `#feature/auth Add JWT token refresh logic`
- Keep description concise but meaningful
- Use imperative mood (Add, Fix, Update, Remove)

## Pull/Merge Request
- Title: `<ticket-id> <ticket-name>`
- Description: Short summary of changes + link to ticket
- Include "This PR/MR closes: <ticket-url>" when applicable
- Target branch: `develop` (unless otherwise configured)

## Rules
- NEVER commit, push, or create MR/PR unless explicitly asked
- Stage specific files by name — never use `git add -A` or `git add .`
- NEVER skip hooks (--no-verify) or bypass signing unless explicitly asked
- NEVER amend commits unless explicitly asked
- NEVER include Co-Authored-By or any trailer lines
- NEVER force push unless explicitly asked and confirmed
- Create NEW commits rather than amending existing ones

## GitHub
- Use `gh` CLI for PR creation
- User is responsible for having `gh` installed and authenticated
- Format: `gh pr create --title "..." --body "..."`

## GitLab
- Use `@zereight/mcp-gitlab` MCP tools for MR creation
- Host and token configured per-project in git-config.json
- Tools: `mcp__gitlab__create_merge_request`, `mcp__gitlab__list_merge_requests`
