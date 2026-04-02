"""Finalization workflow phases: 4.0 (agentic review) through 5 (done)."""
from advance.phases import Phase
from core.db import get_db_ctx, ws_field
from core.global_flags import is_codex_enabled
from core.i18n import t


class AgenticReviewPhase(Phase):
    id = "4.0"
    name = "Agentic Review"

    def progress_key(self, ws):
        return "4.0"

    def validate(self, ws, body, project_path):
        if not ws_field(ws, "codex_review_enabled", 0):
            return True, {}

        with get_db_ctx() as db:
            if not is_codex_enabled(db, default=False):
                return True, {}

        status = ws_field(ws, "codex_review_status", "idle")
        if status == "completed":
            return True, {}
        if status == "failed":
            return False, {"error": t("advance.error.codexReviewFailed", ws["locale"])}
        return False, {"error": t("advance.error.codexReviewPending", ws["locale"])}

    def next_phase(self, ws):
        return "4.1"


class AddressFixPhase(Phase):
    id = "4.1"
    name = "Address Fix"

    def progress_key(self, ws):
        return "4"

    def validate(self, ws, body, project_path):
        return True, {}

    def next_phase(self, ws):
        return "4.2"


class FinalApprovalPhase(Phase):
    id = "4.2"
    name = "Final Approval"
    is_user_gate = True
    approve_target = "5"
    reject_target = "4.1"

    def validate(self, ws, body, project_path):
        return True, {}

    def next_phase(self, ws):
        return "5"


class DonePhase(Phase):
    id = "5"
    name = "Done"

    def validate(self, ws, body, project_path):
        locale = ws["locale"]
        return False, {"error": t("phase.done.complete", locale)}

    def next_phase(self, ws):
        return "5"


PHASES = [AgenticReviewPhase(), AddressFixPhase(), FinalApprovalPhase(), DonePhase()]
