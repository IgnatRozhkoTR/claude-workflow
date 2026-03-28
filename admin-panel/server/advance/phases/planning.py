"""Planning workflow phase: 2.0 (plan validation and approval)."""
from advance.phases import Phase
from core.db import get_db_ctx
from core.i18n import t
from services import plan_service


class PlanningPhase(Phase):
    id = "2.0"
    name = "Planning"

    def progress_key(self, ws):
        return "2"

    def validate(self, ws, body, project_path):
        locale = ws["locale"]

        if ws["scope_status"] != "approved" or ws["plan_status"] != "approved":
            return False, {"error": t("advance.error.scopeAndPlanMustBeApproved", locale)}

        plan = plan_service.get_plan(ws)
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

        with get_db_ctx() as db:
            count = db.execute(
                "SELECT COUNT(*) as cnt FROM acceptance_criteria WHERE workspace_id = ?",
                (ws["id"],)
            ).fetchone()["cnt"]
            pending = db.execute(
                "SELECT COUNT(*) as cnt FROM acceptance_criteria "
                "WHERE workspace_id = ? AND status IN ('proposed', 'rejected')",
                (ws["id"],)
            ).fetchone()["cnt"]

        if count == 0:
            return False, {"message": t("advance.error.noCriteria", locale)}

        if pending > 0:
            return False, {"error": t("gate.error.pendingCriteria", locale, count=pending)}

        return True, {}

    def next_phase(self, ws):
        plan = plan_service.get_plan(ws)
        execution = plan.get("execution", [])
        return execution[0]["id"] + ".0"

    def success_message(self, ws, new_phase):
        locale = ws["locale"]
        plan = plan_service.get_plan(ws)
        execution = plan.get("execution", [])
        return t("advance.success.planValidated", locale, count=len(execution))


PHASES = [PlanningPhase()]
