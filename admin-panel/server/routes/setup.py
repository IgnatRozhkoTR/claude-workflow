"""Setup API routes for running the Claude Code setup skill."""
import json
import logging
import os
import pty
import select
import struct
import fcntl
import termios
import signal
import threading

from flask import Blueprint, request, jsonify
from flask_sock import Sock

from terminal import session_exists, create_session, send_keys, kill_session, tmux_available, send_prompt_when_ready

logger = logging.getLogger(__name__)

_SETUP_SESSION = "ws-setup"

bp = Blueprint('setup', __name__)


def register_setup_ws(app):
    """Register the setup WebSocket route on the Flask app."""
    sock = Sock(app)

    @sock.route('/ws/setup-terminal')
    def setup_terminal_ws(ws):
        if not tmux_available():
            ws.send(json.dumps({'error': 'tmux is not installed. Run: brew install tmux'}))
            return

        if not session_exists(_SETUP_SESSION):
            ws.send(json.dumps({'error': 'No setup session running. Start setup first.'}))
            return

        pid, master_fd = pty.fork()

        if pid == 0:
            os.execvp('tmux', ['tmux', 'attach', '-t', _SETUP_SESSION])

        running = True
        ws_lock = threading.Lock()

        def pty_to_ws():
            """Read from PTY, send to WebSocket."""
            while running:
                try:
                    r, _, _ = select.select([master_fd], [], [], 0.1)
                    if master_fd in r:
                        data = os.read(master_fd, 4096)
                        if not data:
                            break
                        with ws_lock:
                            ws.send(data.decode('utf-8', errors='replace'))
                except (OSError, Exception):
                    break

        reader = threading.Thread(target=pty_to_ws, daemon=True)
        reader.start()

        try:
            while True:
                msg = ws.receive()
                if msg is None:
                    break

                if isinstance(msg, str):
                    if msg.startswith('{'):
                        try:
                            ctrl = json.loads(msg)
                            if 'resize' in ctrl:
                                cols, rows = ctrl['resize']
                                winsize = struct.pack('HHHH', rows, cols, 0, 0)
                                fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)
                                os.kill(pid, signal.SIGWINCH)
                                continue
                        except (json.JSONDecodeError, KeyError):
                            pass
                    os.write(master_fd, msg.encode())
                else:
                    os.write(master_fd, msg)
        except Exception:
            pass
        finally:
            running = False
            try:
                os.close(master_fd)
            except OSError:
                pass
            try:
                os.waitpid(pid, os.WNOHANG)
            except ChildProcessError:
                pass


@bp.route('/api/setup/start', methods=['POST'])
def setup_start():
    """Start a Claude Code setup session in a dedicated tmux pane."""
    if not tmux_available():
        return jsonify({'error': 'tmux is not installed. Run: brew install tmux'}), 503

    data = request.get_json(silent=True) or {}
    modules = data.get('modules', [])
    languages = data.get('languages', [])
    custom_languages = data.get('custom_languages', [])

    logger.info("setup_start: modules=%s languages=%s custom_languages=%s", modules, languages, custom_languages)

    if session_exists(_SETUP_SESSION):
        logger.info("setup_start: killing existing session '%s'", _SETUP_SESSION)
        kill_session(_SETUP_SESSION)

    home_dir = os.path.expanduser("~")
    create_session(_SETUP_SESSION, home_dir)
    logger.info("setup_start: created tmux session '%s' in %s", _SETUP_SESSION, home_dir)

    prompt_lines = [
        "Read the setup skill at ~/.claude/skills/setup/SKILL.md and follow its instructions.",
        "",
        "Configuration:",
        "- Modules to install: " + json.dumps(modules),
        "- Preset verification profiles to assign: " + json.dumps(languages),
        "- Custom verification profiles to create: " + json.dumps(custom_languages),
        "",
        "Complete the setup and report the results.",
    ]
    prompt = "\n".join(prompt_lines).strip()
    logger.info("setup_start: prompt constructed (%d chars)", len(prompt))

    keys_sent = send_keys(_SETUP_SESSION, 'claude --dangerously-skip-permissions')
    logger.info("setup_start: send_keys returned %s for 'claude --dangerously-skip-permissions'", keys_sent)

    send_prompt_when_ready(_SETUP_SESSION, prompt)
    logger.info("setup_start: send_prompt_when_ready dispatched, returning response")

    return jsonify({'session': _SETUP_SESSION, 'status': 'started'})


@bp.route('/api/setup/status', methods=['GET'])
def setup_status():
    """Check if the setup tmux session exists and is running."""
    return jsonify({'running': session_exists(_SETUP_SESSION), 'session': _SETUP_SESSION})
