"""Terminal WebSocket and REST routes for tmux session management."""
import json
import re

from flask import Blueprint, request, jsonify
from flask_sock import Sock

from core.terminal import (
    SESSION_KIND_CLAUDE,
    SESSION_KIND_CODEX_PHASE1,
    TMUX_NOT_INSTALLED,
    build_claude_command,
    build_codex_phase1_command,
    create_session,
    get_session_command,
    kill_session,
    list_sessions,
    run_pty_websocket,
    send_keys,
    send_prompt,
    session_exists,
    session_name,
    tmux_available,
)
from core.db import get_db_ctx, ws_field
from core.global_flags import CODEX_PHASE1_FLAG, is_flag_enabled

_SAFE_NOTIFY_RE = re.compile(r'[^a-zA-Z0-9 .,!?\-_\'\"():;/]')
_MAX_NOTIFY_LENGTH = 300
_CODEX_PHASE1_ALLOWED_PHASES = {'0', '1.0', '1.1', '1.2', '1.3'}

bp = Blueprint('terminal', __name__)


def _validate_session_kind(session_kind):
    if session_kind in (None, "", SESSION_KIND_CLAUDE):
        return SESSION_KIND_CLAUDE
    if session_kind == SESSION_KIND_CODEX_PHASE1:
        return SESSION_KIND_CODEX_PHASE1
    return None


def _terminal_session_name(project, branch, session_kind):
    kind = _validate_session_kind(session_kind)
    if kind is None:
        return None
    return session_name(project, branch, kind=kind)


def register_terminal_ws(app):
    """Register WebSocket routes on the Flask app."""
    sock = Sock(app)

    def _attach_terminal_ws(ws, project, branch, session_kind):
        if not tmux_available():
            ws.send(json.dumps({'error': TMUX_NOT_INSTALLED}))
            return

        name = _terminal_session_name(project, branch, session_kind)
        if not name:
            ws.send(json.dumps({'error': 'Unsupported terminal session kind'}))
            return

        if not session_exists(name):
            ws.send(json.dumps({'error': 'No tmux session. Use Start or Resume first.'}))
            return

        run_pty_websocket(ws, name)

    @sock.route('/ws/terminal/<project>/<branch>')
    def terminal_ws(ws, project, branch):
        _attach_terminal_ws(ws, project, branch, SESSION_KIND_CLAUDE)

    @sock.route('/ws/terminal/<project>/<branch>/<session_kind>')
    def terminal_ws_kind(ws, project, branch, session_kind):
        _attach_terminal_ws(ws, project, branch, session_kind)


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
        return jsonify({'error': TMUX_NOT_INSTALLED}), 503

    with get_db_ctx() as db:
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


@bp.route('/api/ws/<project>/<branch>/terminal/codex-phase1/start', methods=['POST'])
def terminal_start_codex_phase1(project, branch):
    """Create tmux session and start the bounded Codex phase-1 runner."""
    if not tmux_available():
        return jsonify({'error': TMUX_NOT_INSTALLED}), 503

    with get_db_ctx() as db:
        ws = db.execute(
            "SELECT * FROM workspaces WHERE project_id = ? AND sanitized_branch = ?",
            (project, branch)
        ).fetchone()
        if not ws:
            return jsonify({'error': 'Workspace not found'}), 404
        if not is_flag_enabled(db, CODEX_PHASE1_FLAG, default=False):
            return jsonify({'error': 'Codex phase 1 is disabled in global setup'}), 409
        if ws['phase'] not in _CODEX_PHASE1_ALLOWED_PHASES:
            return jsonify({'error': 'Codex phase 1 can only run during preparation phases'}), 409

        name = session_name(project, branch, kind=SESSION_KIND_CODEX_PHASE1)
        working_dir = ws['working_dir']

        if session_exists(name):
            kill_session(name)

        label = ws['sanitized_branch'] or branch
        create_session(name, working_dir, env={'WORKSPACE': label})
        send_keys(name, build_codex_phase1_command())

        return jsonify({
            'session': name,
            'attach_command': f'tmux attach -t {name}',
            'status': 'started',
            'kind': SESSION_KIND_CODEX_PHASE1,
        })


@bp.route('/api/ws/<project>/<branch>/terminal/resume', methods=['POST'])
def terminal_resume(project, branch):
    """Resume Claude Code session in tmux."""
    if not tmux_available():
        return jsonify({'error': TMUX_NOT_INSTALLED}), 503

    with get_db_ctx() as db:
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


@bp.route('/api/ws/<project>/<branch>/command', methods=['GET'])
def get_command_config(project, branch):
    with get_db_ctx() as db:
        ws = db.execute(
            "SELECT claude_command, skip_permissions, restrict_to_workspace, allowed_external_paths FROM workspaces WHERE project_id = ? AND sanitized_branch = ?",
            (project, branch)
        ).fetchone()
        if not ws:
            return jsonify({'error': 'Workspace not found'}), 404
        return jsonify({
            'claude_command': ws['claude_command'] or 'claude',
            'skip_permissions': bool(ws['skip_permissions']),
            'restrict_to_workspace': bool(ws_field(ws, 'restrict_to_workspace', 1)),
            'allowed_external_paths': ws_field(ws, 'allowed_external_paths', '/tmp/')
        })


@bp.route('/api/ws/<project>/<branch>/command', methods=['PUT'])
def update_command_config(project, branch):
    with get_db_ctx() as db:
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


@bp.route('/api/ws/<project>/<branch>/terminal/status', methods=['GET'])
def terminal_status(project, branch):
    """Check if tmux session exists."""
    if not tmux_available():
        return jsonify({'error': TMUX_NOT_INSTALLED}), 503

    session_kind = _validate_session_kind(request.args.get('kind', SESSION_KIND_CLAUDE))
    if session_kind is None:
        return jsonify({'error': 'Unsupported terminal session kind'}), 400

    name = session_name(project, branch, kind=session_kind)
    return jsonify({
        'session': name,
        'exists': session_exists(name),
        'attach_command': f'tmux attach -t {name}',
        'kind': session_kind,
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
    raw_message = data.get('message', 'New review comments have been left. Please check workspace_get_comments.')
    message = _SAFE_NOTIFY_RE.sub('', raw_message)[:_MAX_NOTIFY_LENGTH].strip()

    if not message:
        return jsonify({'error': 'Message is empty after sanitization'}), 400

    send_prompt(name, message)
    return jsonify({'ok': True, 'status': 'notified'})


@bp.route('/api/ws/<project>/<branch>/terminal/kill', methods=['POST'])
def terminal_kill(project, branch):
    """Kill the tmux session."""
    if not tmux_available():
        return jsonify({'error': 'tmux is not installed'}), 503

    data = request.get_json(silent=True) or {}
    session_kind = _validate_session_kind(data.get('kind', SESSION_KIND_CLAUDE))
    if session_kind is None:
        return jsonify({'error': 'Unsupported terminal session kind'}), 400

    name = session_name(project, branch, kind=session_kind)
    if session_exists(name):
        kill_session(name)
    return jsonify({'ok': True, 'status': 'killed', 'kind': session_kind})
    return jsonify({'ok': True, 'status': 'not_found'})
