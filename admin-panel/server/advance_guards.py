"""Cross-cutting advance guards that apply across multiple phases."""
import json
import re
from abc import ABC, abstractmethod

from db import get_db
from phase import Phase


class AdvanceGuard(ABC):
    """A cross-cutting check that may block phase advancement."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this guard."""
        ...

    @abstractmethod
    def evaluate(self, phase: str, ws, body: dict) -> dict:
        """Evaluate this guard. Returns a result dict with 'status' field.

        status: 'skip' (not applicable), 'approved' (passed), 'rejected' (failed)
        On rejection, include 'message' and any relevant detail keys.
        """
        ...


class ResearchProvenGuard(AdvanceGuard):
    """Blocks advancement if any research entries exist that aren't proven.

    Research can be added at any phase. Once added, it must be proven before
    the workflow can proceed. This prevents unverified information from
    influencing implementation decisions. Skips phases before 1.3.
    """

    @property
    def name(self) -> str:
        return "research_proven"

    def evaluate(self, phase: str, ws, body: dict) -> dict:
        if Phase(phase) < "1.3":
            return {"guard": self.name, "status": "skip"}

        db = get_db()
        try:
            rows = db.execute(
                "SELECT id, topic, proven FROM research_entries WHERE workspace_id = ?",
                (ws["id"],)
            ).fetchall()
        finally:
            db.close()

        if not rows:
            return {"guard": self.name, "status": "approved"}

        unproven = [{"id": r["id"], "topic": r["topic"]} for r in rows if r["proven"] == 0]
        rejected = [{"id": r["id"], "topic": r["topic"]} for r in rows if r["proven"] == -1]

        if rejected:
            return {
                "guard": self.name,
                "status": "rejected",
                "message": f"{len(rejected)} research entry/entries have been rejected. Fix findings and re-prove before advancing.",
                "rejected": rejected,
            }

        if unproven:
            return {
                "guard": self.name,
                "status": "rejected",
                "message": f"{len(unproven)} research entry/entries not yet proven. Deploy a research-prover sub-agent before advancing.",
                "unproven": unproven,
            }

        return {"guard": self.name, "status": "approved"}


class PlanApprovedGuard(AdvanceGuard):
    """Blocks advancement if a plan exists but has not been approved by the user.

    Applicable from phase 2.0 onward. Skips phases before 2.0. If no plan is
    present (empty or null), the guard approves — there is nothing to check.
    """

    @property
    def name(self) -> str:
        return "plan_approved"

    def evaluate(self, phase: str, ws, body: dict) -> dict:
        if Phase(phase) < "2.0":
            return {"guard": self.name, "status": "skip"}

        plan_json = ws["plan_json"]
        if not plan_json:
            return {"guard": self.name, "status": "approved"}

        try:
            plan = json.loads(plan_json)
        except (json.JSONDecodeError, TypeError):
            return {"guard": self.name, "status": "approved"}

        execution = plan.get("execution", [])
        if not execution:
            return {"guard": self.name, "status": "approved"}

        if ws["plan_status"] != "approved":
            return {
                "guard": self.name,
                "status": "rejected",
                "message": "Plan has not been approved. User must review and approve the plan in admin panel before advancing.",
            }

        return {"guard": self.name, "status": "approved"}


class ScopeApprovedGuard(AdvanceGuard):
    """Blocks advancement during execution and review phases if scope is not approved.

    Applies to phases starting with '3.' or '4.'. All other phases are skipped.
    """

    @property
    def name(self) -> str:
        return "scope_approved"

    def evaluate(self, phase: str, ws, body: dict) -> dict:
        p = Phase(phase)
        if p < "3.0" or p >= "5":
            return {"guard": self.name, "status": "skip"}

        if ws["scope_status"] != "approved":
            return {
                "guard": self.name,
                "status": "rejected",
                "message": "Scope has not been approved. User must approve the scope in admin panel before advancing.",
            }

        return {"guard": self.name, "status": "approved"}


class ReviewGuard(AdvanceGuard):
    """Blocks advancement if any review items (scope='review') are unresolved.

    Only active at user gate phases where approval happens: code review (3.N.3)
    and final approval (4.2). The user resolves items during review, not before.
    """

    _GATE_PATTERN = re.compile(r'^3\.\d+\.3$')

    @property
    def name(self) -> str:
        return "review_resolved"

    def evaluate(self, phase: str, ws, body: dict) -> dict:
        if phase != "4.2" and not self._GATE_PATTERN.match(phase):
            return {"guard": self.name, "status": "skip"}

        db = get_db()
        try:
            row = db.execute(
                "SELECT COUNT(*) as cnt FROM discussions "
                "WHERE workspace_id = ? AND scope = 'review' AND parent_id IS NULL AND status != 'resolved'",
                (ws["id"],)
            ).fetchone()
        finally:
            db.close()

        count = row["cnt"] if row else 0
        if count > 0:
            return {
                "guard": self.name,
                "status": "rejected",
                "message": f"{count} review item(s) still unresolved. All review items must be resolved by the user before advancing.",
                "unresolved_count": count,
            }

        return {"guard": self.name, "status": "approved"}


class GuardOrchestrator:
    def __init__(self, guards: list[AdvanceGuard]):
        self._guards = guards

    def evaluate_all(self, phase: str, ws, body: dict) -> list[dict]:
        """Run all guards, collect all results. Does NOT stop at first failure."""
        results = []
        for guard in self._guards:
            result = guard.evaluate(phase, ws, body)
            results.append(result)
        return results


GUARD_ORCHESTRATOR = GuardOrchestrator([
    ResearchProvenGuard(),
    PlanApprovedGuard(),
    ScopeApprovedGuard(),
    ReviewGuard(),
])
