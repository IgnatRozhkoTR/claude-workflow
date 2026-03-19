"""Terminal WebSocket and REST routes for tmux session management."""
import os
import pty
import select
import struct
import fcntl
import termios
import threading
import json
import signal

from flask import Blueprint, request, jsonify
from flask_sock import Sock

from terminal import session_name, session_exists, create_session, send_keys, kill_session, tmux_available
from db import get_db

bp = Blueprint('terminal', __name__)


def register_terminal_ws(app):
    """Register WebSocket routes on the Flask app."""
    sock = Sock(app)

    @sock.route('/ws/terminal/<project>/<branch>')
    def terminal_ws(ws, project, branch):
        if not tmux_available():
            ws.send(json.dumps({'error': 'tmux is not installed. Run: brew install tmux'}))
            return

        name = session_name(project, branch)

        if not session_exists(name):
            ws.send(json.dumps({'error': 'No tmux session. Use Start or Resume first.'}))
            return

        pid, master_fd = pty.fork()

        if pid == 0:
            os.execvp('tmux', ['tmux', 'attach', '-t', name])

        running = True

        def pty_to_ws():
            """Read from PTY, send to WebSocket."""
            while running:
                try:
                    r, _, _ = select.select([master_fd], [], [], 0.1)
                    if master_fd in r:
                        data = os.read(master_fd, 4096)
                        if not data:
                            break
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


@bp.route('/api/ws/<project>/<branch>/terminal/start', methods=['POST'])
def terminal_start(project, branch):
    """Create tmux session and start Claude Code."""
    if not tmux_available():
        return jsonify({'error': 'tmux is not installed. Run: brew install tmux'}), 503

    db = get_db()
    try:
        ws = db.execute(
            "SELECT * FROM workspaces WHERE project_id = ? AND sanitized_branch = ?",
            (project, branch)
        ).fetchone()
        if not ws:
            return jsonify({'error': 'Workspace not found'}), 404

        name = session_name(project, branch)
        working_dir = ws['working_dir']

        if session_exists(name):
            kill_session(name)

        create_session(name, working_dir)
        send_keys(name, 'claude --dangerously-skip-permissions')

        return jsonify({
            'session': name,
            'attach_command': f'tmux attach -t {name}',
            'status': 'started'
        })
    finally:
        db.close()


@bp.route('/api/ws/<project>/<branch>/terminal/resume', methods=['POST'])
def terminal_resume(project, branch):
    """Resume Claude Code session in tmux."""
    if not tmux_available():
        return jsonify({'error': 'tmux is not installed. Run: brew install tmux'}), 503

    db = get_db()
    try:
        ws = db.execute(
            "SELECT * FROM workspaces WHERE project_id = ? AND sanitized_branch = ?",
            (project, branch)
        ).fetchone()
        if not ws:
            return jsonify({'error': 'Workspace not found'}), 404

        name = session_name(project, branch)
        working_dir = ws['working_dir']
        session_id = ws['session_id']

        if not session_exists(name):
            create_session(name, working_dir)

        if session_id:
            send_keys(name, f'claude --dangerously-skip-permissions -r {session_id}')
        else:
            send_keys(name, 'claude --dangerously-skip-permissions')

        return jsonify({
            'session': name,
            'attach_command': f'tmux attach -t {name}',
            'status': 'resumed'
        })
    finally:
        db.close()


@bp.route('/api/ws/<project>/<branch>/terminal/status', methods=['GET'])
def terminal_status(project, branch):
    """Check if tmux session exists."""
    if not tmux_available():
        return jsonify({'error': 'tmux is not installed. Run: brew install tmux'}), 503

    name = session_name(project, branch)
    return jsonify({
        'session': name,
        'exists': session_exists(name),
        'attach_command': f'tmux attach -t {name}'
    })
