---
name: setup
description: Initial workspace setup — configures modules and verification profiles based on user selections from the admin panel
user_invocable: false
tools_required:
  - Bash
  - Read
  - Edit
  - Write
---

# Setup — Workspace Configuration Assistant

This skill is invoked automatically by the admin panel's setup wizard. It receives a configuration payload describing which modules to install and which verification profiles to configure.

## Input

The setup configuration is passed as the initial prompt. It contains:
- **modules to enable**: List of module IDs to enable (e.g., `["telegram"]`)
- **modules to disable**: List of module IDs to disable (e.g., `["other_module"]`)
- **languages**: List of language profile configurations to set up

## Execution Flow

### Phase 1: Module Configuration

For each module in the `modules to enable` list:

1. Read the module's skill file at `~/.claude/modules/<module_id>/SKILL.md`
2. Read the skill thoroughly — understand its `enable` section before doing anything
3. Follow the `enable` instructions exactly as written in the skill (the `enable` command handles install if needed, then activates the integration)
4. If the skill defines a `status` command, run it after enabling to verify success
5. If enabling fails:
   - Capture the full error output
   - Report it clearly: what failed, what the error was, what the user can do
   - Continue to the next module — do not abort the entire setup

For each module in the `modules to disable` list:

1. Read the module's skill file at `~/.claude/modules/<module_id>/SKILL.md`
2. Read the skill thoroughly — understand its `disable` section before doing anything
3. Follow the `disable` instructions exactly as written in the skill
4. If disabling fails:
   - Capture the full error output
   - Report it clearly: what failed, what the error was, what the user can do
   - Continue to the next module — do not abort the entire setup

### Phase 2: Verification Profile Validation and Setup

Detect the device environment before processing any profiles:
- Run `uname -s` to determine OS (Darwin = macOS, Linux = Linux)
- On macOS, check if `brew` is available (`which brew`)
- On Linux, identify the package manager (`which apt`, `which dnf`, `which pacman`)
- Note the detected environment — it will affect install commands throughout this phase

#### For Preset / System Profiles

For each selected preset language profile:

1. Check if a matching verification profile already exists via MCP workspace tools
2. If it exists, do not recreate it — proceed to validate it
3. **Validate each step in the profile actually works on this device:**
   - Run the step's `install_check_command` (e.g., `which java`, `which python3`)
   - If the check fails (tool not found):
     - Run the step's `install_command` to install it
     - If the install command fails, inform the user clearly: what tool is missing, what command was attempted, what they need to do manually (e.g., download from official site, accept a license, log in)
   - After installation (or if already present), run a quick smoke test of the main command to confirm it works:
     - e.g., `java --version`, `python3 --version`, `node --version`, `go version`
   - If the smoke test fails despite the tool being "installed", report the specific output and warn the user
4. Check whether the profile's commands are compatible with this device:
   - Watch for hardcoded paths that may not exist (e.g., `/usr/local/bin/...` on macOS with Apple Silicon vs Intel)
   - Watch for Linux-only or macOS-only commands
   - If a command references a path or tool that doesn't exist on this device, warn the user and suggest what needs to be adjusted
5. Assign the profile to the workspace after validation

#### For Custom Language Configurations

For each custom language configuration:

1. Create the verification profile via `workspace_create_verification_profile` MCP tool.
   **If the configuration includes LSP settings**, pass them in the same call:
   ```
   workspace_create_verification_profile(
     name="Go",
     language="go",
     description="Go compilation, lint, and test",
     lsp_command="gopls",
     lsp_args='["serve"]',
     lsp_install_check_command="which gopls",
     lsp_install_command="go install golang.org/x/tools/gopls@latest"
   )
   ```
   The `lsp_command` parameter is **required** for the LSP button to appear in the admin panel header. If omitted, the profile will work for verification but LSP integration will be missing.
2. For each tool specified in the configuration:
   - If `install_check_command` is not provided, auto-detect it: use `which <tool>` as the default
   - If `install_command` is not provided, auto-detect based on OS and package manager:
     - macOS with brew: `brew install <tool>`
     - Debian/Ubuntu: `sudo apt install -y <tool>`
     - Fedora/RHEL: `sudo dnf install -y <tool>`
   - Add the tool as a verification step via `workspace_add_verification_step` MCP tool
   - Run the `install_check_command` to verify the tool is present
   - If the tool is missing:
     - Run the `install_command`
     - If it fails, explain what the user needs to do manually (license acceptance, account creation, manual download, etc.)
   - Run a smoke test of the tool to confirm it works end-to-end
3. Assign the profile to the workspace

### LSP Server Setup

For each profile that includes LSP configuration (`lsp_server` field in the configuration):

1. Check if the LSP server binary is installed by running the `lsp_install_check_command` from the profile, or `which <lsp_server>` if no check command is provided
2. If not installed, run the `lsp_install` command from the configuration
   - If the install command fails, report clearly: what binary is missing, what was attempted, and what the user must do manually
3. Smoke-test the server to confirm it runs: try `<lsp_server> --help` or `<lsp_server> --version`
   - If the binary exits with a non-zero code but the LSP protocol requires no flags, treat it as passing if the binary is found
   - If the binary is not found at all, report it as a failure
4. Report LSP server status alongside the profile status: installed / not installed / failed

For custom profiles with LSP:

1. The user provides the binary name (`lsp_server`) and install command (`lsp_install`) in the configuration
2. Follow the same check → install → smoke-test flow described above
3. **CRITICAL**: Pass LSP parameters directly in `workspace_create_verification_profile` — they CANNOT be added after creation. The following parameters map from the user's configuration:
   - `lsp_server` → `lsp_command` parameter
   - `lsp_install` → `lsp_install_command` parameter
   - Auto-derive `lsp_install_check_command` as `which <lsp_server>` if not provided
   - Set `lsp_args` if the LSP protocol requires specific flags (e.g., `'["--stdio"]'`)
4. After creation, verify the profile ID was returned and the LSP button appears in the admin panel

### Phase 3: Final Verification

1. List all configured modules and their status (enabled / disabled / failed / skipped)
2. List all configured verification profiles with the status of each step:
   - Step name, install check result, smoke test result
3. Run a quick verification pass of each profile to confirm all steps pass cleanly
4. Report a summary:
   - What succeeded
   - What failed or is degraded
   - Any manual actions the user needs to take, listed clearly and specifically

## Module Directory Structure

Modules live at `~/.claude/modules/`. Each module directory contains:
- `SKILL.md` — The skill definition with install/configure/status instructions
- Additional files needed by the module (scripts, configs, etc.)

## Verification Profile Configuration

When creating custom verification profiles, each language configuration includes:
- `name` — Profile display name (e.g., "Go")
- `language` — Language key (e.g., "go")
- `tools` — List of tools to add as verification steps, each with:
  - `name` — Step name (e.g., "Compilation")
  - `command` — The verification command (e.g., `go build ./...`)
  - `install_check_command` — Command to check if tool is installed (e.g., `which go`)
  - `install_command` — Command to install the tool if missing
  - `fail_severity` — `"blocking"` or `"warning"`

## Important Notes

- Profiles are global, not workspace-specific — they apply across all projects once configured
- Be adaptive to the device: never assume a fixed OS, package manager, or binary location
- Never skip a failure silently — always report what happened and what the user can do about it
- If the user needs to take a manual action (accept a license, log in to a registry, download a proprietary SDK), explain exactly what to do with enough detail that they can act without guessing
- This skill should minimize interaction, but it must not hide problems behind false success messages
