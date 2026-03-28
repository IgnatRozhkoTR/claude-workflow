"""Preparation workflow phases: 0 (init) through 1.4 (preparation review gate)."""
import json

from advance.phases import Phase
from core.db import get_db_ctx
from core.i18n import t


class InitPhase(Phase):
    id = "0"
    name = "Init"

    def validate(self, ws, body, project_path):
        return True, {}

    def next_phase(self, ws):
        return "1.0"


class AssessmentPhase(Phase):
    id = "1.0"
    name = "Assessment"

    def progress_key(self, ws):
        return "1.0"

    def validate(self, ws, body, project_path):
        locale = ws["locale"]

        with get_db_ctx() as db:
            count = db.execute(
                "SELECT COUNT(*) as cnt FROM discussions "
                "WHERE workspace_id = ? AND scope IS NULL AND parent_id IS NULL AND type = 'research'",
                (ws["id"],)
            ).fetchone()["cnt"]

        if count == 0:
            return False, {"message": t("advance.error.noResearchDiscussion", locale)}

        return True, {}

    def next_phase(self, ws):
        return "1.1"


class ResearchPhase(Phase):
    id = "1.1"
    name = "Research"

    def validate(self, ws, body, project_path):
        locale = ws["locale"]
        # Check explicit confirmation
        if not body.get("no_further_research_needed"):
            return False, {"message": t("advance.error.noFurtherResearch", locale)}

        with get_db_ctx() as db:
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


class ProverPhase(Phase):
    id = "1.2"
    name = "Research Proving"

    def progress_key(self, ws):
        return "1"

    def validate(self, ws, body, project_path):
        locale = ws["locale"]
        with get_db_ctx() as db:
            rows = db.execute(
                "SELECT id, topic, proven FROM research_entries WHERE workspace_id = ?",
                (ws["id"],)
            ).fetchall()

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


class ImpactAnalysisPhase(Phase):
    id = "1.3"
    name = "Impact Analysis"

    def progress_key(self, ws):
        return "1.3"

    def validate(self, ws, body, project_path):
        return True, {}

    def next_phase(self, ws):
        return "1.4"


class PreparationReviewPhase(Phase):
    id = "1.4"
    name = "Preparation Review"
    is_user_gate = True
    approve_target = "2.0"
    reject_target = "1.1"

    def progress_key(self, ws):
        return "1.3"

    def validate(self, ws, body, project_path):
        return True, {}

    def next_phase(self, ws):
        return "2.0"


PHASES = [
    InitPhase(),
    AssessmentPhase(),
    ResearchPhase(),
    ProverPhase(),
    ImpactAnalysisPhase(),
    PreparationReviewPhase(),
]
