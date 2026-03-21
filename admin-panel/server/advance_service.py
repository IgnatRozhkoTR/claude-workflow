"""Phase advancement domain logic: advancers, transitions, and shared advance functions.

All domain logic for phase advancement lives here. Route handlers in routes/advance.py
are thin wrappers that delegate to this module.
"""
import json
import logging
import re
import secrets
from abc import ABC, abstractmethod
from datetime import datetime

logger = logging.getLogger(__name__)

from criteria_validators import validate_all
from db import get_db
from helpers import workspace_dir, run_git, match_scope_pattern, DEFAULT_SOURCE_BRANCH
import scope_service
from i18n import t


class PhaseAdvancer(ABC):
    @abstractmethod
    def validate(self, ws, body, project_path):
        """Returns (ok: bool, details: dict)."""
        ...

    @abstractmethod
    def next_phase(self, ws):
        """Returns the next phase string."""
        ...

    def progress_key(self, ws):
        """Return the progress key required before this advance, or None if not needed."""
        return None

    def success_message(self, ws, new_phase):
        locale = ws["locale"]
        phase_guides = {
            "1.0": t("phase.guide.1_0", locale),
            "1.1": t("phase.guide.1_1", locale),
            "1.2": t("phase.guide.1_2", locale),
            "1.3": t("phase.guide.1_3", locale),
            "1.4": t("phase.guide.1_4", locale),
            "2.0": t("phase.guide.2_0", locale),
            "2.1": t("phase.guide.2_1", locale),
            "4.0": t("phase.guide.4_0", locale),
            "4.1": t("phase.guide.4_1", locale),
            "4.2": t("phase.guide.4_2", locale),
            "5": t("phase.guide.5", locale),
        }
        match = re.match(r'^3\.(\d+)\.(\d+)$', new_phase)
        if match:
            n, k = match.group(1), match.group(2)
            sub_guides = {
                "0": t("phase.guide.sub.0", locale),
                "1": t("phase.guide.sub.1", locale, n=n),
                "2": t("phase.guide.sub.2", locale),
                "3": t("phase.guide.sub.3", locale),
                "4": t("phase.guide.sub.4", locale, n=n),
            }
            guide = sub_guides.get(k, "")
            return t("advance.success.advancedWithGuide", locale, phase=new_phase, guide=guide) if guide else t("advance.success.advanced", locale, phase=new_phase)
        guide = phase_guides.get(new_phase, "")
        return t("advance.success.advancedWithGuide", locale, phase=new_phase, guide=guide) if guide else t("advance.success.advanced", locale, phase=new_phase)


class InitAdvancer(PhaseAdvancer):
    def validate(self, ws, body, project_path):
        return True, {}

    def next_phase(self, ws):
        return "1.0"


class AssessmentAdvancer(PhaseAdvancer):
    def progress_key(self, ws):
        return "1.0"

    def validate(self, ws, body, project_path):
        locale = ws["locale"]

        # Check that at least one research discussion exists
        db = get_db()
        try:
            count = db.execute(
                "SELECT COUNT(*) as cnt FROM discussions "
                "WHERE workspace_id = ? AND scope IS NULL AND parent_id IS NULL AND type = 'research'",
                (ws["id"],)
            ).fetchone()["cnt"]
        finally:
            db.close()

        if count == 0:
            return False, {"message": t("advance.error.noResearchDiscussion", locale)}

        return True, {}

    def next_phase(self, ws):
        return "1.1"


class ResearchAdvancer(PhaseAdvancer):
    def validate(self, ws, body, project_path):
        locale = ws["locale"]
        # Check explicit confirmation
        if not body.get("no_further_research_needed"):
            return False, {"message": t("advance.error.noFurtherResearch", locale)}

        db = get_db()
        try:
            # Check all unresolved research discussions have linked research
            unresolved_research_discussions = db.execute(
                "SELECT id, text FROM discussions "
                "WHERE workspace_id = ? AND scope IS NULL AND parent_id IS NULL "
                "AND type = 'research' AND status = 'open'",
                (ws["id"],)
            ).fetchall()

            missing = []
            for disc in unresolved_research_discussions:
                linked = db.execute(
                    "SELECT COUNT(*) as cnt FROM research_entries "
                    "WHERE workspace_id = ? AND discussion_id = ?",
                    (ws["id"], disc["id"])
                ).fetchone()["cnt"]
                if linked == 0:
                    missing.append({"discussion_id": disc["id"], "text": disc["text"][:100]})

            if missing:
                return False, {
                    "message": t("advance.error.missingResearch", locale),
                    "missing": missing
                }

            # Existing validation: check research entries exist and are valid
            rows = db.execute(
                "SELECT id, findings_json FROM research_entries WHERE workspace_id = ?",
                (ws["id"],)
            ).fetchall()
        finally:
            db.close()

        if not rows:
            return False, {"message": t("advance.error.noResearchEntries", locale)}

        errors = []
        for row in rows:
            try:
                findings = json.loads(row["findings_json"])
            except (json.JSONDecodeError, TypeError):
                errors.append({"entry_id": row["id"], "issues": [t("advance.error.invalidJson", locale)]})
                continue

            if not isinstance(findings, list) or not findings:
                errors.append({"entry_id": row["id"], "issues": [t("advance.error.emptyFindings", locale)]})
                continue

            entry_issues = []
            for fi, finding in enumerate(findings):
                if not isinstance(finding.get("summary"), str) or not finding.get("summary"):
                    entry_issues.append(t("advance.error.missingSummary", locale, index=fi))

                proof = finding.get("proof")
                if not isinstance(proof, dict):
                    entry_issues.append(t("advance.error.missingProof", locale, index=fi))
                    continue

                proof_type = proof.get("type", "code")
                if proof_type == "code":
                    if not proof.get("file"):
                        entry_issues.append(t("advance.error.codeProofMissingFile", locale, index=fi))
                    if not proof.get("line_start") or not proof.get("line_end"):
                        entry_issues.append(t("advance.error.codeProofMissingLineRange", locale, index=fi))
                elif proof_type == "web":
                    if not proof.get("url"):
                        entry_issues.append(t("advance.error.webProofMissingUrl", locale, index=fi))
                elif proof_type == "diff":
                    if not proof.get("commit"):
                        entry_issues.append(t("advance.error.diffProofMissingCommit", locale, index=fi))

            if entry_issues:
                errors.append({"entry_id": row["id"], "issues": entry_issues})

        if errors:
            return False, {"errors": errors}
        return True, {}

    def next_phase(self, ws):
        return "1.2"


class ProverAdvancer(PhaseAdvancer):
    def progress_key(self, ws):
        return "1"

    def validate(self, ws, body, project_path):
        locale = ws["locale"]
        db = get_db()
        try:
            rows = db.execute(
                "SELECT id, topic, proven FROM research_entries WHERE workspace_id = ?",
                (ws["id"],)
            ).fetchall()
        finally:
            db.close()

        if not rows:
            return False, {"message": t("advance.error.noResearchToProve", locale)}

        unproven = [{"id": r["id"], "topic": r["topic"]} for r in rows if r["proven"] != 1]
        rejected = [{"id": r["id"], "topic": r["topic"]} for r in rows if r["proven"] == -1]

        if rejected:
            return False, {
                "message": t("advance.error.rejectedEntries", locale, count=len(rejected)),
                "rejected": rejected,
            }

        if unproven:
            return False, {
                "message": t("advance.error.unprovenEntries", locale, count=len(unproven)),
                "unproven": unproven,
            }

        return True, {}

    def next_phase(self, ws):
        return "1.3"


class ImpactAnalysisAdvancer(PhaseAdvancer):
    def progress_key(self, ws):
        return "1.3"

    def validate(self, ws, body, project_path):
        return True, {}

    def next_phase(self, ws):
        return "1.4"


class PreparationReviewAdvancer(PhaseAdvancer):
    def progress_key(self, ws):
        return "1.3"

    def validate(self, ws, body, project_path):
        return True, {}

    def next_phase(self, ws):
        return "2.0"


class PlanAdvancer(PhaseAdvancer):
    def progress_key(self, ws):
        return "2"

    def validate(self, ws, body, project_path):
        locale = ws["locale"]
        plan = json.loads(ws["plan_json"]) if ws["plan_json"] else {}
        execution = plan.get("execution", [])

        if not execution:
            return False, {"message": t("advance.error.noPlanExecution", locale)}

        issues = []
        expected_index = 1
        for i, item in enumerate(execution):
            item_id = item.get("id", "")
            expected_id = f"3.{expected_index}"
            if item_id != expected_id:
                issues.append(t("advance.error.planItemIdMismatch", locale, i=i, expected_id=expected_id, actual_id=item_id))

            if not isinstance(item.get("name"), str) or not item.get("name"):
                issues.append(t("advance.error.planItemMissingName", locale, i=i))

            tasks = item.get("tasks", [])
            if not isinstance(tasks, list) or not tasks:
                issues.append(t("advance.error.planItemTasksMustBeArray", locale, i=i))
            else:
                for ti, task in enumerate(tasks):
                    if not isinstance(task.get("title"), str) or not task.get("title"):
                        issues.append(t("advance.error.planTaskMissingTitle", locale, i=i, ti=ti))
                    if not isinstance(task.get("files"), list):
                        issues.append(t("advance.error.planTaskFilesMustBeArray", locale, i=i, ti=ti))
                    if not isinstance(task.get("agent"), str) or not task.get("agent"):
                        issues.append(t("advance.error.planTaskMissingAgent", locale, i=i, ti=ti))

            expected_index += 1

        if issues:
            return False, {"message": t("advance.error.planValidationFailed", locale), "issues": issues}

        db = get_db()
        try:
            count = db.execute(
                "SELECT COUNT(*) as cnt FROM acceptance_criteria WHERE workspace_id = ?",
                (ws["id"],)
            ).fetchone()["cnt"]
        finally:
            db.close()

        if count == 0:
            return False, {"message": t("advance.error.noCriteria", locale)}

        return True, {}

    def next_phase(self, ws):
        return "2.1"

    def success_message(self, ws, new_phase):
        locale = ws["locale"]
        plan = json.loads(ws["plan_json"]) if ws["plan_json"] else {}
        execution = plan.get("execution", [])
        return t("advance.success.planValidated", locale, count=len(execution))


class AgenticReviewAdvancer(PhaseAdvancer):
    def progress_key(self, ws):
        return "4.0"

    def validate(self, ws, body, project_path):
        return True, {}

    def next_phase(self, ws):
        return "4.1"


class AddressFixAdvancer(PhaseAdvancer):
    def progress_key(self, ws):
        return "4"

    def validate(self, ws, body, project_path):
        return True, {}

    def next_phase(self, ws):
        return "4.2"


class DoneAdvancer(PhaseAdvancer):
    def validate(self, ws, body, project_path):
        locale = ws["locale"]
        return False, {"error": t("phase.done.complete", locale)}

    def next_phase(self, ws):
        return "5"


class ExecutionAdvancer(PhaseAdvancer):
    def __init__(self, phase):
        parts = phase.split(".")
        self._n = int(parts[1])
        self._k = int(parts[2])
        self._phase = phase

    def progress_key(self, ws):
        if self._k == 4:
            return f"3.{self._n}"
        return None

    def validate(self, ws, body, project_path):
        self._project_path = project_path
        if self._k == 0:
            return self._validate_implementation(ws, project_path)
        if self._k in (1, 2):
            return True, {}
        if self._k == 4:
            return self._validate_commit(ws, body, project_path)
        return True, {}

    def next_phase(self, ws):
        n = self._n
        if self._k == 0:
            return f"3.{n}.1"
        if self._k == 1:
            return self._route_after_validation(ws)
        if self._k == 2:
            return f"3.{n}.3"
        if self._k == 4:
            return self._next_after_commit(ws)
        return f"3.{n}.{self._k + 1}"

    def _validate_implementation(self, ws, project_path):
        scope_map = json.loads(ws["scope_json"]) if ws["scope_json"] else {}
        phase = ws["phase"]
        must_patterns = scope_service.get_phase_must_patterns(scope_map, phase)

        if not must_patterns:
            return True, {}

        try:
            source = ws["source_branch"] or DEFAULT_SOURCE_BRANCH
        except (IndexError, KeyError):
            source = DEFAULT_SOURCE_BRANCH

        all_changed = set()

        ok, stdout, _ = run_git(ws["working_dir"], "diff", "--name-only", f"{source}..HEAD")
        if not ok:
            ok, stdout, _ = run_git(ws["working_dir"], "diff", "--name-only", f"origin/{source}..HEAD")
        if not ok:
            ok, stdout, _ = run_git(ws["working_dir"], "diff", "--name-only", "HEAD")
        if ok:
            all_changed.update(line.strip() for line in stdout.splitlines() if line.strip())

        ok2, stdout2, _ = run_git(ws["working_dir"], "diff", "--cached", "--name-only")
        if ok2:
            all_changed.update(line.strip() for line in stdout2.splitlines() if line.strip())

        # Unstaged modifications to tracked files
        ok2b, stdout2b, _ = run_git(ws["working_dir"], "diff", "--name-only")
        if ok2b:
            all_changed.update(line.strip() for line in stdout2b.splitlines() if line.strip())

        ok3, stdout3, _ = run_git(ws["working_dir"], "ls-files", "--others", "--exclude-standard")
        if ok3:
            all_changed.update(line.strip() for line in stdout3.splitlines() if line.strip())

        changed_files = list(all_changed)

        for pattern in must_patterns:
            matched = False
            for changed_file in changed_files:
                if pattern.endswith("/"):
                    match_pattern = pattern.rstrip("/") + "/**"
                else:
                    match_pattern = pattern
                if match_scope_pattern(changed_file, match_pattern):
                    matched = True
                    break
            if not matched:
                return False, {"message": t("advance.error.noMustScopeChanges", ws["locale"], pattern=pattern)}

        return True, {}

    def _route_after_validation(self, ws):
        n = self._n
        ws_dir = workspace_dir(self._project_path, ws["branch"])
        validation_path = ws_dir / "validation" / f"3.{n}.json"
        if validation_path.exists():
            try:
                data = json.loads(validation_path.read_text())
                if data.get("status") == "clean":
                    return f"3.{n}.3"
            except (json.JSONDecodeError, OSError):
                pass
        return f"3.{n}.2"

    def _validate_commit(self, ws, body, project_path):
        locale = ws["locale"]
        commit_hash = body.get("commit_hash", "")
        if not commit_hash:
            return False, {"message": t("advance.error.commitHashRequired", locale)}

        ok, _, _ = run_git(ws["working_dir"], "cat-file", "-t", commit_hash)
        if not ok:
            return False, {"message": t("advance.error.commitNotFound", locale, commit_hash=commit_hash)}

        db = get_db()
        try:
            used = db.execute(
                "SELECT id FROM phase_history WHERE workspace_id = ? AND commit_hash = ?",
                (ws["id"], commit_hash)
            ).fetchone()
        finally:
            db.close()

        if used:
            return False, {"message": t("advance.error.commitAlreadyUsed", locale, commit_hash=commit_hash)}

        plan = json.loads(ws["plan_json"]) if ws["plan_json"] else {}
        execution = plan.get("execution", [])
        max_n = 0
        for item in execution:
            item_id = item.get("id", "")
            m = re.match(r'^3\.(\d+)$', item_id)
            if m:
                max_n = max(max_n, int(m.group(1)))

        if self._n >= max_n:
            db = get_db()
            try:
                all_passed, results = validate_all(db, ws["id"], ws["working_dir"])
            finally:
                db.close()

            if not all_passed:
                failed = [r for r in results if not r["passed"]]
                messages = [f"  - {r['type']}: {r['message']}" for r in failed]
                return False, {
                    "message": t("advance.error.acceptanceCriteriaNotMet", locale, messages="\n".join(messages))
                }

        return True, {}

    def _next_after_commit(self, ws):
        n = self._n
        plan = json.loads(ws["plan_json"]) if ws["plan_json"] else {}
        execution = plan.get("execution", [])

        max_n = 0
        for item in execution:
            item_id = item.get("id", "")
            m = re.match(r'^3\.(\d+)$', item_id)
            if m:
                max_n = max(max_n, int(m.group(1)))

        if n >= max_n:
            return "4.0"
        return f"3.{n + 1}.0"


ADVANCER_CLASSES = {
    "0": InitAdvancer,
    "1.0": AssessmentAdvancer,
    "1.1": ResearchAdvancer,
    "1.2": ProverAdvancer,
    "1.3": ImpactAnalysisAdvancer,
    "1.4": PreparationReviewAdvancer,
    "2.0": PlanAdvancer,
    "4.0": AgenticReviewAdvancer,
    "4.1": AddressFixAdvancer,
    "5": DoneAdvancer,
}


def is_user_gate(phase):
    if phase in ("1.4", "2.1", "4.2"):
        return True
    return bool(re.match(r'^3\.\d+\.3$', phase))


def check_progress(workspace_id, phase_key):
    db = get_db()
    try:
        row = db.execute(
            "SELECT summary FROM progress_entries WHERE workspace_id = ? AND phase = ?",
            (workspace_id, phase_key)
        ).fetchone()
        return bool(row and row["summary"].strip())
    finally:
        db.close()


def get_advancer(phase):
    cls = ADVANCER_CLASSES.get(phase)
    if cls:
        return cls()
    if re.match(r'^3\.\d+\.\d+$', phase):
        return ExecutionAdvancer(phase)
    return None


def transition_phase(db, ws, new_phase, clear_nonce=False, commit_hash=None):
    """Shared phase transition: update phase, record history, manage nonce.

    Returns True if the transition succeeded, False if the phase was already changed
    by a concurrent request (optimistic lock via WHERE phase = current).
    """
    rows = db.execute(
        "UPDATE workspaces SET phase = ? WHERE id = ? AND phase = ?",
        (new_phase, ws["id"], ws["phase"])
    ).rowcount
    if rows == 0:
        return False

    db.execute(
        "INSERT INTO phase_history (workspace_id, from_phase, to_phase, time, commit_hash) VALUES (?, ?, ?, ?, ?)",
        (ws["id"], ws["phase"], new_phase, datetime.now().isoformat(), commit_hash)
    )

    if clear_nonce:
        db.execute("UPDATE workspaces SET gate_nonce = NULL WHERE id = ?", (ws["id"],))
    elif is_user_gate(new_phase):
        nonce = secrets.token_urlsafe(32)
        db.execute("UPDATE workspaces SET gate_nonce = ? WHERE id = ?", (nonce, ws["id"]))

    return True


def approve_gate(ws, token, commit_message=None):
    """Approve a user gate. Returns a result dict with an embedded status_code key."""
    locale = ws["locale"]
    phase = ws["phase"]
    if not is_user_gate(phase):
        return {"error": t("gate.error.notAtUserGate", locale), "status_code": 400}

    if not token:
        return {"error": t("gate.error.nonceRequired", locale), "status_code": 400}
    if token != ws["gate_nonce"]:
        return {"error": t("gate.error.invalidNonce", locale), "status_code": 403}

    from advance_guards import GUARD_ORCHESTRATOR
    guard_results = GUARD_ORCHESTRATOR.evaluate_all(phase, ws, {})
    rejected = [r for r in guard_results if r["status"] == "rejected"]
    if rejected:
        return {"error": rejected[0]["message"], "guard_errors": rejected, "status_code": 422}

    db = get_db()
    try:
        if phase == "1.4":
            new_phase = "2.0"
        elif phase == "2.1":
            plan = json.loads(ws["plan_json"]) if ws["plan_json"] else {}
            execution = plan.get("execution", [])
            if not execution:
                return {"error": t("gate.error.noExecutionPlan", locale), "status_code": 400}

            pending = db.execute(
                "SELECT COUNT(*) as cnt FROM acceptance_criteria "
                "WHERE workspace_id = ? AND status IN ('proposed', 'rejected')",
                (ws["id"],)
            ).fetchone()
            if pending and pending["cnt"] > 0:
                return {
                    "error": t("gate.error.pendingCriteria", locale, count=pending["cnt"]),
                    "status_code": 400,
                }

            new_phase = execution[0]["id"] + ".0"
        elif re.match(r'^3\.\d+\.3$', phase):
            n = phase.split(".")[1]
            new_phase = f"3.{n}.4"
            if commit_message:
                db.execute(
                    "UPDATE workspaces SET commit_message = ? WHERE id = ?",
                    (commit_message, ws["id"])
                )
        elif phase == "4.2":
            new_phase = "5"
        else:
            return {"error": t("gate.error.unknownGate", locale), "status_code": 400}

        if not transition_phase(db, ws, new_phase, clear_nonce=True):
            return {"error": t("gate.error.phaseAlreadyChanged", locale), "status_code": 409}

        db.commit()
        return {"phase": new_phase, "previous_phase": phase, "status": "ok", "status_code": 200}
    finally:
        db.close()


def reject_gate(ws, token, comments=""):
    """Reject a user gate. Returns a result dict with an embedded status_code key."""
    locale = ws["locale"]
    phase = ws["phase"]
    if not is_user_gate(phase):
        return {"error": t("gate.error.notAtUserGate", locale), "status_code": 400}

    if not token:
        return {"error": t("gate.error.nonceRequired", locale), "status_code": 400}
    if token != ws["gate_nonce"]:
        return {"error": t("gate.error.invalidNonce", locale), "status_code": 403}

    if phase == "1.4":
        new_phase = "1.1"
    elif phase == "2.1":
        new_phase = "2.0"
    elif re.match(r'^3\.\d+\.3$', phase):
        n = phase.split(".")[1]
        new_phase = f"3.{n}.2"
    elif phase == "4.2":
        new_phase = "4.1"
    else:
        return {"error": t("gate.error.unknownGate", locale), "status_code": 400}

    db = get_db()
    try:
        if not transition_phase(db, ws, new_phase, clear_nonce=True):
            return {"error": t("gate.error.phaseAlreadyChanged", locale), "status_code": 409}

        if comments:
            db.execute(
                "INSERT INTO discussions (workspace_id, scope, target, text, author, status, created_at) "
                "VALUES (?, 'phase', ?, ?, 'user', 'open', ?)",
                (ws["id"], f"reject:{phase}", comments, datetime.now().isoformat())
            )

        db.commit()
        return {"phase": new_phase, "previous_phase": phase, "status": "rejected", "status_code": 200}
    finally:
        db.close()


def _notify_yolo_approve(ws, phase):
    """Send a YOLO auto-approval notification to the tmux session."""
    try:
        from terminal import send_keys, session_name, session_exists
        name = session_name(ws["project_id"], ws["sanitized_branch"])
        if session_exists(name):
            send_keys(name, f"[YOLO] Auto-approved phase {phase}. Proceeding.")
    except Exception:
        logger.warning("Failed to send YOLO auto-approve notification", exc_info=True)


def perform_advance(ws, project_path, body=None):
    """Core advance logic. Returns (result_dict, http_status_code).

    Can be called from Flask route or MCP tool.
    Manages its own DB connection for the transaction.
    """
    body = body or {}
    phase = ws["phase"]

    locale = ws["locale"]

    if is_user_gate(phase):
        yolo = ws["yolo_mode"] if "yolo_mode" in ws.keys() else 0
        if yolo:
            nonce = ws["gate_nonce"]
            if nonce:
                result = approve_gate(ws, nonce)
                status_code = result.pop("status_code", 200)
                if status_code == 200:
                    _notify_yolo_approve(ws, phase)
                    return result, status_code
        return {"error": t("advance.error.awaitingUserApproval", locale), "phase": phase}, 409

    advancer = get_advancer(phase)
    if not advancer:
        return {"error": t("advance.error.noAdvancerForPhase", locale, phase=phase)}, 400

    ok, details = advancer.validate(ws, body, project_path)
    if not ok:
        return {"phase": phase, "status": "blocked", **details}, 422

    required_key = advancer.progress_key(ws)
    if required_key and not check_progress(ws["id"], required_key):
        return {
            "phase": phase,
            "status": "blocked",
            "message": t("advance.error.noProgress", locale, phase=required_key, next=advancer.next_phase(ws)),
        }, 422

    from advance_guards import GUARD_ORCHESTRATOR
    guard_results = GUARD_ORCHESTRATOR.evaluate_all(phase, ws, body)
    rejected = [r for r in guard_results if r["status"] == "rejected"]
    if rejected:
        return {"phase": phase, "status": "blocked", "guard_errors": rejected}, 422

    new_phase = advancer.next_phase(ws)

    db = get_db()
    try:
        if not transition_phase(db, ws, new_phase, commit_hash=body.get("commit_hash")):
            return {"error": t("advance.error.phaseAlreadyChanged", locale)}, 409

        db.commit()

        yolo_enabled = ws["yolo_mode"] if "yolo_mode" in ws.keys() else 0
        if is_user_gate(new_phase) and yolo_enabled:
            ws_fresh = db.execute(
                "SELECT * FROM workspaces WHERE project_id = ? AND sanitized_branch = ?",
                (ws["project_id"], ws["sanitized_branch"])
            ).fetchone()
            nonce = ws_fresh["gate_nonce"] if ws_fresh else None
            if nonce:
                approve_result = approve_gate(ws_fresh, nonce)
                approve_status = approve_result.pop("status_code", 200)
                if approve_status == 200:
                    _notify_yolo_approve(ws_fresh, new_phase)
                    return approve_result, approve_status

        code = 202 if is_user_gate(new_phase) else 200
        result = {
            "phase": new_phase,
            "previous_phase": phase,
            "message": advancer.success_message(ws, new_phase),
            "status": "awaiting_approval" if code == 202 else "ok",
        }
        return result, code
    finally:
        db.close()
