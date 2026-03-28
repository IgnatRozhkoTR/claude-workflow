"""Setup API routes for running the Claude Code setup skill."""
import json
import logging
import os
from pathlib import Path

from flask import Blueprint, request, jsonify
from flask_sock import Sock

from core.terminal import session_exists, create_session, send_keys, kill_session, tmux_available, send_prompt_when_ready, run_pty_websocket, TMUX_NOT_INSTALLED

_MODULES_DIR = Path(os.path.expanduser("~/.claude/modules"))

logger = logging.getLogger(__name__)

_SETUP_SESSION = "ws-setup"

bp = Blueprint('setup', __name__)


def register_setup_ws(app):
    """Register the setup WebSocket route on the Flask app."""
    sock = Sock(app)

    @sock.route('/ws/setup-terminal')
    def setup_terminal_ws(ws):
        if not tmux_available():
            ws.send(json.dumps({'error': TMUX_NOT_INSTALLED}))
            return

        if not session_exists(_SETUP_SESSION):
            ws.send(json.dumps({'error': 'No setup session running. Start setup first.'}))
            return

        run_pty_websocket(ws, _SETUP_SESSION)


@bp.route('/api/setup/start', methods=['POST'])
def setup_start():
    """Start a Claude Code setup session in a dedicated tmux pane."""
    if not tmux_available():
        return jsonify({'error': TMUX_NOT_INSTALLED}), 503

    data = request.get_json(silent=True) or {}
    modules = data.get('modules', [])
    languages = data.get('languages', [])
    custom_languages = data.get('custom_languages', [])

    logger.info("setup_start: modules_to_enable=%s languages=%s custom_languages=%s", modules, languages, custom_languages)

    available_module_ids = []
    if _MODULES_DIR.is_dir():
        for entry in sorted(_MODULES_DIR.iterdir()):
            if entry.is_dir() and (entry / "SKILL.md").is_file():
                available_module_ids.append(entry.name)

    selected_set = set(modules)
    modules_to_disable = [m for m in available_module_ids if m not in selected_set]

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
        "- Modules to enable: " + json.dumps(modules),
        "- Modules to disable: " + json.dumps(modules_to_disable),
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
