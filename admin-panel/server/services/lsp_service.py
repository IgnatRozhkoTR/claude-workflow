"""LSP server lifecycle management: spawn, track, communicate, and teardown."""
import atexit
import json
import logging
import os
import select
import signal
import subprocess
import threading
import time
from datetime import datetime

logger = logging.getLogger(__name__)

_LSP_PROCESSES = {}
_PROCESS_LOCKS = {}
_request_id_lock = threading.Lock()
_request_id_counter = 0


def _next_request_id():
    global _request_id_counter
    with _request_id_lock:
        _request_id_counter += 1
        return _request_id_counter


def _encode_lsp_message(obj):
    """Format a Python dict as a Content-Length-delimited JSON-RPC message."""
    body = json.dumps(obj, separators=(",", ":"))
    body_bytes = body.encode("utf-8")
    header = f"Content-Length: {len(body_bytes)}\r\n\r\n"
    return header.encode("ascii") + body_bytes


def _has_buffered_data(stream):
    """Check if the stream's OS pipe has data available without blocking."""
    buf = getattr(stream, "buffer", stream)
    raw = getattr(buf, "raw", None)
    fd = None
    if raw is not None and hasattr(raw, "fileno"):
        try:
            fd = raw.fileno()
        except (ValueError, OSError):
            return False
    elif hasattr(buf, "fileno"):
        try:
            fd = buf.fileno()
        except (ValueError, OSError):
            return False
    if fd is None:
        return False
    readable, _, _ = select.select([fd], [], [], 0)
    return len(readable) > 0


def _wait_for_readable(stream, timeout):
    """Return True if *stream* has buffered data or becomes OS-readable within *timeout* seconds."""
    if _has_buffered_data(stream):
        return True
    try:
        readable, _, _ = select.select([stream], [], [], timeout)
        return bool(readable)
    except (ValueError, OSError):
        return False


def _read_lsp_message(stdout, timeout=None):
    """Read one Content-Length-delimited JSON-RPC message from *stdout*.

    Returns the parsed dict, or None on EOF / protocol error / timeout.
    When *timeout* is given, waits at most that many seconds for data
    before returning None.
    """
    if timeout is not None and not _wait_for_readable(stdout, timeout):
        return None

    headers = {}
    while True:
        line = stdout.readline()
        if not line:
            return None
        line_str = line.decode("ascii", errors="replace").strip()
        if not line_str:
            break
        if ":" in line_str:
            key, _, value = line_str.partition(":")
            headers[key.strip().lower()] = value.strip()

    length_str = headers.get("content-length")
    if length_str is None:
        logger.warning("LSP message missing Content-Length header")
        return None

    try:
        length = int(length_str)
    except ValueError:
        logger.warning("Invalid Content-Length value: %s", length_str)
        return None

    body = stdout.read(length)
    if len(body) < length:
        return None

    return json.loads(body.decode("utf-8"))


def _process_key(project_id, profile_id):
    return (str(project_id), int(profile_id))


def _is_pid_alive(pid):
    """Return True if a process with *pid* exists."""
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _get_lock(key):
    """Return (and lazily create) a threading.Lock for the given process key."""
    return _PROCESS_LOCKS.setdefault(key, threading.Lock())


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def get_project_lsp_profiles(db, project_id):
    """Return LSP-capable profiles assigned to *project_id* with instance status."""
    rows = db.execute(
        "SELECT pp.id AS assignment_id, pp.lsp_enabled, pp.subpath, "
        "       vp.id AS profile_id, vp.name, vp.language, "
        "       vp.lsp_command, vp.lsp_args, vp.lsp_install_check_command, "
        "       vp.lsp_install_command, vp.lsp_workspace_config, vp.lsp_port, "
        "       li.pid, li.port AS instance_port, li.status AS instance_status, "
        "       li.started_at, li.error_message "
        "FROM project_verification_profiles pp "
        "JOIN verification_profiles vp ON pp.profile_id = vp.id "
        "LEFT JOIN lsp_instances li ON li.project_id = pp.project_id AND li.profile_id = vp.id "
        "WHERE pp.project_id = ? AND vp.lsp_command IS NOT NULL",
        (project_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def get_lsp_status(db, project_id):
    """Return status of all LSP instances for *project_id*, reaping dead processes."""
    rows = db.execute(
        "SELECT li.*, vp.name AS profile_name "
        "FROM lsp_instances li "
        "JOIN verification_profiles vp ON li.profile_id = vp.id "
        "WHERE li.project_id = ?",
        (project_id,)
    ).fetchall()

    results = []
    for row in rows:
        entry = dict(row)
        if entry["status"] == "running" and entry["pid"]:
            if not _is_pid_alive(entry["pid"]):
                db.execute(
                    "UPDATE lsp_instances SET status = 'error', error_message = 'Process died unexpectedly' "
                    "WHERE project_id = ? AND profile_id = ?",
                    (project_id, entry["profile_id"])
                )
                entry["status"] = "error"
                entry["error_message"] = "Process died unexpectedly"
                key = _process_key(project_id, entry["profile_id"])
                _LSP_PROCESSES.pop(key, None)
        results.append(entry)
    return results


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

def _initialize_lsp_server(key, workspace_path):
    """Perform the LSP initialize handshake (initialize request + initialized notification).

    Returns the initialize response dict on success, or raises RuntimeError on failure.
    """
    entry = _LSP_PROCESSES.get(key)
    if entry is None:
        raise RuntimeError("LSP process not tracked")

    process = entry["process"]
    if process.poll() is not None:
        raise RuntimeError("LSP process exited before initialization")

    request_id = _next_request_id()
    init_request = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "initialize",
        "params": {
            "processId": os.getpid(),
            "rootUri": f"file://{workspace_path}",
            "rootPath": workspace_path,
            "capabilities": {
                "textDocument": {
                    "definition": {"dynamicRegistration": False},
                    "hover": {
                        "dynamicRegistration": False,
                        "contentFormat": ["markdown", "plaintext"],
                    },
                    "references": {"dynamicRegistration": False},
                    "synchronization": {
                        "dynamicRegistration": False,
                        "didSave": True,
                        "willSave": False,
                    },
                    "completion": {
                        "dynamicRegistration": False,
                        "completionItem": {"snippetSupport": False},
                    },
                },
            },
            "workspaceFolders": [
                {"uri": f"file://{workspace_path}", "name": os.path.basename(workspace_path)}
            ],
        },
    }

    try:
        process.stdin.write(_encode_lsp_message(init_request))
        process.stdin.flush()
    except (BrokenPipeError, OSError) as exc:
        raise RuntimeError(f"Failed to send initialize request: {exc}")

    deadline = time.time() + 30
    response = None
    while True:
        remaining = deadline - time.time()
        if remaining <= 0:
            raise RuntimeError("Timed out waiting for initialize response (30s)")
        response = _read_lsp_message(process.stdout, timeout=remaining)
        if response is None:
            raise RuntimeError("LSP server closed stdout before responding to initialize")
        if response.get("id") == request_id:
            break
        if "method" in response:
            logger.debug("LSP init: skipping notification %s", response.get("method"))

    if "error" in response:
        raise RuntimeError(f"LSP initialize returned error: {response['error']}")

    initialized_notification = {
        "jsonrpc": "2.0",
        "method": "initialized",
        "params": {},
    }
    try:
        process.stdin.write(_encode_lsp_message(initialized_notification))
        process.stdin.flush()
    except (BrokenPipeError, OSError) as exc:
        raise RuntimeError(f"Failed to send initialized notification: {exc}")

    logger.info("LSP server initialized successfully for key=%s", key)
    return response


def _drain_stderr(process, key):
    """Consume stderr in a background daemon thread to prevent pipe deadlock."""

    def _reader():
        try:
            for raw_line in process.stderr:
                line = raw_line.decode("utf-8", errors="replace").rstrip()
                if line:
                    logger.debug("LSP stderr [%s]: %s", key, line)
        except (ValueError, OSError):
            pass

    thread = threading.Thread(target=_reader, daemon=True)
    thread.start()


def start_lsp_server(db, project_id, profile_id, workspace_path):
    """Spawn an LSP server for the given project/profile and track it."""
    profile = db.execute(
        "SELECT * FROM verification_profiles WHERE id = ?", (profile_id,)
    ).fetchone()
    if not profile:
        return {"error": "profile_not_found"}

    if not profile["lsp_command"]:
        return {"error": "profile_has_no_lsp_command"}

    key = _process_key(project_id, profile_id)

    existing = db.execute(
        "SELECT pid, status FROM lsp_instances WHERE project_id = ? AND profile_id = ?",
        (project_id, profile_id)
    ).fetchone()
    if existing and existing["status"] == "running" and existing["pid"]:
        if _is_pid_alive(existing["pid"]):
            return {"ok": True, "status": "already_running", "pid": existing["pid"]}

    cmd = [profile["lsp_command"]] + json.loads(profile["lsp_args"] or "[]")
    logger.info("Starting LSP server: %s (project=%s, profile=%s)", cmd, project_id, profile_id)

    db.execute(
        "INSERT INTO lsp_instances (project_id, profile_id, status) "
        "VALUES (?, ?, 'starting') "
        "ON CONFLICT(project_id, profile_id) DO UPDATE SET status = 'starting', error_message = NULL",
        (project_id, profile_id)
    )
    db.commit()

    try:
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=workspace_path,
        )
        _drain_stderr(process, key)
    except FileNotFoundError:
        error_msg = f"LSP command not found: {profile['lsp_command']}"
        logger.error(error_msg)
        db.execute(
            "UPDATE lsp_instances SET status = 'error', error_message = ? "
            "WHERE project_id = ? AND profile_id = ?",
            (error_msg, project_id, profile_id)
        )
        return {"error": error_msg}
    except OSError as exc:
        error_msg = f"Failed to start LSP server: {exc}"
        logger.error(error_msg)
        db.execute(
            "UPDATE lsp_instances SET status = 'error', error_message = ? "
            "WHERE project_id = ? AND profile_id = ?",
            (error_msg, project_id, profile_id)
        )
        return {"error": error_msg}

    _LSP_PROCESSES[key] = {
        "process": process,
        "profile_id": profile_id,
        "project_id": project_id,
        "workspace_path": workspace_path,
    }
    _get_lock(key)

    try:
        _initialize_lsp_server(key, workspace_path)
    except RuntimeError as exc:
        error_msg = f"LSP initialization failed: {exc}"
        logger.error(error_msg)
        _LSP_PROCESSES.pop(key, None)
        _PROCESS_LOCKS.pop(key, None)
        try:
            process.terminate()
            process.wait(timeout=5)
        except (subprocess.TimeoutExpired, OSError):
            process.kill()
            try:
                process.wait(timeout=3)
            except (subprocess.TimeoutExpired, OSError):
                pass
        db.execute(
            "UPDATE lsp_instances SET status = 'error', error_message = ? "
            "WHERE project_id = ? AND profile_id = ?",
            (error_msg, project_id, profile_id),
        )
        return {"error": error_msg}

    now = datetime.now().isoformat()
    db.execute(
        "UPDATE lsp_instances SET pid = ?, status = 'running', started_at = ?, error_message = NULL "
        "WHERE project_id = ? AND profile_id = ?",
        (process.pid, now, project_id, profile_id)
    )

    logger.info("LSP server started: pid=%d (project=%s, profile=%s)", process.pid, project_id, profile_id)
    return {"ok": True, "status": "running", "pid": process.pid}


def stop_lsp_server(db, project_id, profile_id):
    """Gracefully stop an LSP server (SIGTERM then SIGKILL)."""
    key = _process_key(project_id, profile_id)
    entry = _LSP_PROCESSES.pop(key, None)

    if entry is None:
        db.execute(
            "UPDATE lsp_instances SET status = 'stopped', pid = NULL "
            "WHERE project_id = ? AND profile_id = ?",
            (project_id, profile_id)
        )
        return {"ok": True, "status": "stopped", "note": "no_tracked_process"}

    process = entry["process"]
    try:
        process.terminate()
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        logger.warning("LSP server pid=%d did not terminate, sending SIGKILL", process.pid)
        process.kill()
        process.wait(timeout=3)
    except OSError:
        pass

    _PROCESS_LOCKS.pop(key, None)

    db.execute(
        "UPDATE lsp_instances SET status = 'stopped', pid = NULL "
        "WHERE project_id = ? AND profile_id = ?",
        (project_id, profile_id)
    )

    logger.info("LSP server stopped (project=%s, profile=%s)", project_id, profile_id)
    return {"ok": True, "status": "stopped"}


# ---------------------------------------------------------------------------
# Batch operations
# ---------------------------------------------------------------------------

def start_all_lsp_servers(db, project_id, workspace_path):
    """Start LSP servers for every enabled profile of *project_id*."""
    profiles = db.execute(
        "SELECT vp.id AS profile_id, vp.name "
        "FROM project_verification_profiles pp "
        "JOIN verification_profiles vp ON pp.profile_id = vp.id "
        "WHERE pp.project_id = ? AND pp.lsp_enabled = 1 AND vp.lsp_command IS NOT NULL",
        (project_id,)
    ).fetchall()

    results = []
    for p in profiles:
        result = start_lsp_server(db, project_id, p["profile_id"], workspace_path)
        result["profile_id"] = p["profile_id"]
        result["profile_name"] = p["name"]
        results.append(result)
    db.commit()
    return results


def stop_all_lsp_servers(db, project_id):
    """Stop all running LSP servers for *project_id*."""
    instances = db.execute(
        "SELECT profile_id FROM lsp_instances WHERE project_id = ? AND status = 'running'",
        (project_id,)
    ).fetchall()

    results = []
    for inst in instances:
        result = stop_lsp_server(db, project_id, inst["profile_id"])
        result["profile_id"] = inst["profile_id"]
        results.append(result)
    db.commit()
    return results


# ---------------------------------------------------------------------------
# Install check
# ---------------------------------------------------------------------------

def check_lsp_installed(profile):
    """Return True if the LSP tool required by *profile* is installed."""
    cmd = profile.get("lsp_install_check_command")
    if not cmd:
        return True
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


# ---------------------------------------------------------------------------
# JSON-RPC communication
# ---------------------------------------------------------------------------

def send_lsp_request(project_id, profile_id, method, params):
    """Send a JSON-RPC request and return the parsed response."""
    key = _process_key(project_id, profile_id)
    entry = _LSP_PROCESSES.get(key)
    if entry is None:
        return {"error": "lsp_server_not_running"}

    lock = _get_lock(key)
    request_id = _next_request_id()
    message = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
        "params": params or {},
    }

    with lock:
        process = entry["process"]
        if process.poll() is not None:
            _LSP_PROCESSES.pop(key, None)
            return {"error": "lsp_server_process_exited"}

        try:
            process.stdin.write(_encode_lsp_message(message))
            process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            _LSP_PROCESSES.pop(key, None)
            return {"error": f"failed_to_write: {exc}"}

        deadline = time.time() + 10
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                return {"error": "lsp_response_timeout"}
            response = _read_lsp_message(process.stdout, timeout=remaining)
            if response is None:
                if time.time() >= deadline:
                    return {"error": "lsp_response_timeout"}
                return {"error": "no_response_from_lsp_server"}
            if response.get("id") == request_id:
                return response
            if "method" in response:
                logger.debug("LSP notification (skipped): %s", response.get("method"))


def send_lsp_notification(project_id, profile_id, method, params):
    """Send a JSON-RPC notification (no response expected)."""
    key = _process_key(project_id, profile_id)
    entry = _LSP_PROCESSES.get(key)
    if entry is None:
        return {"error": "lsp_server_not_running"}

    lock = _get_lock(key)
    message = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params or {},
    }

    with lock:
        process = entry["process"]
        if process.poll() is not None:
            _LSP_PROCESSES.pop(key, None)
            return {"error": "lsp_server_process_exited"}

        try:
            process.stdin.write(_encode_lsp_message(message))
            process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            _LSP_PROCESSES.pop(key, None)
            return {"error": f"failed_to_write: {exc}"}

    return {"ok": True}


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

def shutdown_all():
    """Terminate every tracked LSP server. Called via atexit on app exit."""
    keys = list(_LSP_PROCESSES.keys())
    for key in keys:
        entry = _LSP_PROCESSES.pop(key, None)
        if entry is None:
            continue
        process = entry["process"]
        try:
            process.terminate()
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
        except OSError:
            pass
    logger.info("All LSP servers shut down (%d total)", len(keys))


atexit.register(shutdown_all)
