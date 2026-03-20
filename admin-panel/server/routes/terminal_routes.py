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

from terminal import session_name, session_exists, create_session, send_keys, kill_session, tmux_available, build_claude_command, list_sessions, get_session_command
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


@bp.route('/api/terminal/sessions', methods=['GET'])
def list_terminal_sessions():
    """List all running tmux sessions."""
    sessions = list_sessions()
    for s in sessions:
        s['command'] = get_session_command(s['name'])
    return jsonify(sessions)


@bp.route('/api/terminal/sessions/<name>/kill', methods=['POST'])
def kill_terminal_session_by_name(name):
    """Kill a tmux session by name."""
    if not session_exists(name):
        return jsonify({'ok': False, 'status': 'not_found'}), 404
    kill_session(name)
    return jsonify({'ok': True, 'status': 'killed'})


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

        data = request.get_json(silent=True)
        channels = data.get('channels', '') if data else ''

        label = ws['sanitized_branch'] or branch
        create_session(name, working_dir, env={'WORKSPACE': label})
        send_keys(name, build_claude_command(ws, channels=channels))

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

        data = request.get_json(silent=True)
        channels = data.get('channels', '') if data else ''

        created = False
        if not session_exists(name):
            label = ws['sanitized_branch'] or branch
            create_session(name, working_dir, env={'WORKSPACE': label})
            send_keys(name, build_claude_command(ws, resume=True, channels=channels))
            created = True

        return jsonify({
            'session': name,
            'attach_command': f'tmux attach -t {name}',
            'status': 'created' if created else 'attached'
        })
    finally:
        db.close()


@bp.route('/api/ws/<project>/<branch>/command', methods=['GET'])
def get_command_config(project, branch):
    db = get_db()
    try:
        ws = db.execute(
            "SELECT claude_command, skip_permissions, restrict_to_workspace, allowed_external_paths FROM workspaces WHERE project_id = ? AND sanitized_branch = ?",
            (project, branch)
        ).fetchone()
        if not ws:
            return jsonify({'error': 'Workspace not found'}), 404
        return jsonify({
            'claude_command': ws['claude_command'] or 'claude',
            'skip_permissions': bool(ws['skip_permissions']),
            'restrict_to_workspace': bool(ws['restrict_to_workspace']) if 'restrict_to_workspace' in ws.keys() else True,
            'allowed_external_paths': ws['allowed_external_paths'] if 'allowed_external_paths' in ws.keys() else '/tmp/'
        })
    finally:
        db.close()


@bp.route('/api/ws/<project>/<branch>/command', methods=['PUT'])
def update_command_config(project, branch):
    db = get_db()
    try:
        data = request.get_json() or {}

        updates = []
        params = []

        if 'claude_command' in data:
            cmd = (data['claude_command'] or '').strip() or 'claude'
            updates.append('claude_command = ?')
            params.append(cmd)

        if 'skip_permissions' in data:
            updates.append('skip_permissions = ?')
            params.append(1 if data['skip_permissions'] else 0)

        if 'restrict_to_workspace' in data:
            updates.append('restrict_to_workspace = ?')
            params.append(1 if data['restrict_to_workspace'] else 0)

        if 'allowed_external_paths' in data:
            updates.append('allowed_external_paths = ?')
            params.append((data['allowed_external_paths'] or '').strip() or '/tmp/')

        if not updates:
            return jsonify({'error': 'No fields to update'}), 400

        params.extend([project, branch])
        db.execute(
            "UPDATE workspaces SET " + ", ".join(updates) + " WHERE project_id = ? AND sanitized_branch = ?",
            params
        )
        db.commit()

        return jsonify({'ok': True})
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


@bp.route('/api/ws/<project>/<branch>/terminal/notify', methods=['POST'])
def terminal_notify(project, branch):
    """Send a notification message to the active tmux session."""
    if not tmux_available():
        return jsonify({'error': 'tmux is not installed'}), 503

    name = session_name(project, branch)
    if not session_exists(name):
        return jsonify({'error': 'No active tmux session'}), 404

    data = request.get_json() or {}
    message = data.get('message', 'New review comments have been left. Please check workspace_get_comments.')

    send_keys(name, message)
    return jsonify({'ok': True, 'status': 'notified'})


@bp.route('/api/ws/<project>/<branch>/terminal/kill', methods=['POST'])
def terminal_kill(project, branch):
    """Kill the tmux session."""
    if not tmux_available():
        return jsonify({'error': 'tmux is not installed'}), 503

    name = session_name(project, branch)
    if session_exists(name):
        kill_session(name)
        return jsonify({'ok': True, 'status': 'killed'})
    return jsonify({'ok': True, 'status': 'not_found'})
