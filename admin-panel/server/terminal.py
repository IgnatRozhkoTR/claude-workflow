"""Tmux session management for browser-based terminal access."""
import subprocess
import re
import shutil


def tmux_available():
    """Check if tmux is installed and accessible."""
    return shutil.which('tmux') is not None


def sanitize_session_name(name):
    """Make a tmux-safe session name from branch/project."""
    return re.sub(r'[^a-zA-Z0-9_-]', '-', name)[:50]


def session_name(project_id, branch):
    """Generate tmux session name for a workspace."""
    return 'ws-' + sanitize_session_name(project_id + '-' + branch)


def session_exists(name):
    """Check if a tmux session exists."""
    result = subprocess.run(['tmux', 'has-session', '-t', name],
                            capture_output=True)
    return result.returncode == 0


def create_session(name, working_dir):
    """Create a new detached tmux session."""
    subprocess.run(['tmux', 'new-session', '-d', '-s', name, '-c', working_dir],
                   check=True)
    subprocess.run(['tmux', 'set-option', '-t', name, 'mouse', 'on'], capture_output=True)
    subprocess.run(['tmux', 'set-option', '-t', name, 'set-clipboard', 'on'], capture_output=True)
    # Override WheelUpPane to always enter copy mode (fixes Claude Code stealing scroll)
    subprocess.run(['tmux', 'bind-key', '-n', 'WheelUpPane',
                    'if-shell', '-F', '#{pane_in_mode}',
                    'send-keys -M',
                    'copy-mode -e; send-keys -M'], capture_output=True)
    # Copy mouse selection to system clipboard, stay in copy mode
    subprocess.run(['tmux', 'bind-key', '-T', 'copy-mode', 'MouseDragEnd1Pane',
                    'send-keys', '-X', 'copy-pipe-and-cancel', 'pbcopy'], capture_output=True)
    subprocess.run(['tmux', 'bind-key', '-T', 'copy-mode-vi', 'MouseDragEnd1Pane',
                    'send-keys', '-X', 'copy-pipe-and-cancel', 'pbcopy'], capture_output=True)
    # Intuitive pane split shortcuts
    subprocess.run(['tmux', 'bind-key', 'h', 'split-window', '-h'], capture_output=True)
    subprocess.run(['tmux', 'bind-key', 'v', 'split-window', '-v'], capture_output=True)


def send_keys(name, command):
    """Send keystrokes to a tmux session."""
    if not session_exists(name):
        return False
    subprocess.run(['tmux', 'send-keys', '-t', name, command, 'Enter'])
    return True


def kill_session(name):
    """Kill a tmux session."""
    subprocess.run(['tmux', 'kill-session', '-t', name], capture_output=True)


def build_claude_command(ws, resume=False, channels=None):
    """Build the full claude command from workspace config."""
    cmd = (ws['claude_command'] if 'claude_command' in ws.keys() else None) or 'claude'
    skip = ws['skip_permissions'] if 'skip_permissions' in ws.keys() else 1
    if skip:
        cmd += ' --dangerously-skip-permissions'
    ch = channels if channels is not None else ws.get('channels', '')
    if ch:
        cmd += f' --channels {ch}'
    if resume:
        session_id = ws['session_id'] if 'session_id' in ws.keys() else None
        if session_id:
            cmd += ' -r ' + session_id
    return cmd


def get_active_session(project_id, branch):
    """Get info about the workspace's tmux session."""
    name = session_name(project_id, branch)
    return {
        'name': name,
        'exists': session_exists(name),
        'attach_command': f'tmux attach -t {name}'
    }
