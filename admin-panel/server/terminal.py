"""Tmux session management for browser-based terminal access."""
import logging
import os
import subprocess
import re
import shutil
import tempfile

logger = logging.getLogger(__name__)


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


def send_prompt(name, text):
    """Send a multi-line prompt to a tmux session using buffer paste.

    Unlike send_keys which interprets newlines as Enter keystrokes,
    this uses tmux load-buffer + paste-buffer for clean multi-line delivery.
    """
    if not session_exists(name):
        return False

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(text)
            tmp_path = f.name

        subprocess.run(['tmux', 'load-buffer', tmp_path], check=True)
        subprocess.run(['tmux', 'paste-buffer', '-t', name], check=True)
        subprocess.run(['tmux', 'send-keys', '-t', name, 'Enter'])
        return True
    except Exception:
        logger.warning("Failed to send prompt to %s", name, exc_info=True)
        return False
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


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
        logger.warning("Failed to list tmux sessions", exc_info=True)
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
        logger.warning("Failed to get tmux session command", exc_info=True)
        return ''


def get_active_session(project_id, branch):
    """Get info about the workspace's tmux session."""
    name = session_name(project_id, branch)
    return {
        'name': name,
        'exists': session_exists(name),
        'attach_command': f'tmux attach -t {name}'
    }


def send_prompt_when_ready(target_session, prompt, max_wait=30, poll_interval=1):
    """
    Poll the tmux session until Claude Code is ready to accept input,
    then paste the prompt and submit it.

    Runs in a background thread so it doesn't block the HTTP response.
    """
    import threading

    def _poll_and_send():
        import time

        logger.info("send_prompt_when_ready: started polling for session '%s' (max_wait=%ds)", target_session, max_wait)

        elapsed = 0
        poll_count = 0
        while elapsed < max_wait:
            time.sleep(poll_interval)
            elapsed += poll_interval
            poll_count += 1

            if not session_exists(target_session):
                logger.warning("send_prompt_when_ready: session '%s' disappeared after %ds, aborting", target_session, elapsed)
                return

            try:
                result = subprocess.run(
                    ['tmux', 'capture-pane', '-t', target_session, '-p'],
                    capture_output=True, text=True, timeout=5
                )
                ready = _is_claude_ready(result.stdout)
                logger.info("send_prompt_when_ready: poll #%d at %ds — ready=%s", poll_count, elapsed, ready)
                if ready:
                    logger.info("send_prompt_when_ready: Claude is ready in session '%s', sending prompt", target_session)
                    break
            except Exception:
                logger.warning("send_prompt_when_ready: failed to capture pane for '%s' at poll #%d", target_session, poll_count, exc_info=True)
                continue
        else:
            logger.warning("send_prompt_when_ready: timed out after %ds waiting for Claude Code in session '%s', sending prompt anyway", max_wait, target_session)

        success = send_prompt(target_session, prompt)
        logger.info("send_prompt_when_ready: send_prompt returned %s for session '%s'", success, target_session)

    thread = threading.Thread(target=_poll_and_send, daemon=True)
    thread.start()
    logger.info("send_prompt_when_ready: background thread started for session '%s'", target_session)


def _strip_ansi(text):
    """Remove ANSI escape sequences from text."""
    return re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', text).strip()


def _is_claude_ready(pane_content):
    """Check if Claude Code's input field is present in the terminal.

    Detects the input prompt pattern: a line containing ❯ bordered
    by lines of ─ box-drawing characters.
    """
    if not pane_content:
        return False

    clean = _strip_ansi(pane_content)
    lines = clean.split('\n')

    for i, line in enumerate(lines):
        if '❯' in line:
            # Found the prompt character — verify it's bordered by ─ lines
            # Check nearby lines (within 2 lines above/below) for border
            has_border = False
            for j in range(max(0, i - 2), min(len(lines), i + 3)):
                if j != i and '─' * 5 in lines[j]:
                    has_border = True
                    break
            if has_border:
                return True

    return False
