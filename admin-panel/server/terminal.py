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


def create_session(name, working_dir, env=None):
    """Create a new detached tmux session."""
    subprocess.run(['tmux', 'new-session', '-d', '-s', name, '-c', working_dir],
                   check=True)
    if env:
        for key, value in env.items():
            subprocess.run(['tmux', 'setenv', '-t', name, key, value], capture_output=True)
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
    label = ws['sanitized_branch'] if 'sanitized_branch' in ws.keys() else None
    session_id = ws['session_id'] if 'session_id' in ws.keys() else None
    if resume and session_id:
        cmd += f' -r {session_id}'
    elif resume and label:
        cmd += f' -r {label}'
    elif label:
        cmd += f' -n {label}'
    return cmd


def list_sessions():
    """List all running tmux sessions."""
    if not tmux_available():
        return []
    try:
        result = subprocess.run(
            ['tmux', 'list-sessions', '-F', '#{session_name}||#{session_attached}||#{session_activity}'],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            return []
        sessions = []
        for line in result.stdout.strip().split('\n'):
            if not line:
                continue
            parts = line.split('||')
            if len(parts) < 3:
                continue
            name = parts[0]
            attached = int(parts[1]) > 0
            sessions.append({
                'name': name,
                'attached': attached
            })
        return sessions
    except Exception:
        return []


def get_session_command(name):
    """Get the first line of the session pane (the command that started it)."""
    try:
        result = subprocess.run(
            ['tmux', 'capture-pane', '-t', name, '-p', '-S', '0', '-E', '2'],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            return ''
        lines = [l.strip() for l in result.stdout.split('\n') if l.strip()]
        for line in lines:
            if 'claude' in line.lower():
                return line
        return lines[0] if lines else ''
    except Exception:
        return ''


def get_active_session(project_id, branch):
    """Get info about the workspace's tmux session."""
    name = session_name(project_id, branch)
    return {
        'name': name,
        'exists': session_exists(name),
        'attach_command': f'tmux attach -t {name}'
    }
