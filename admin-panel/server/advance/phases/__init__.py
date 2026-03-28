"""Phase definitions for the governed workflow.

Each workflow sub-phase is a Phase subclass that encapsulates:
- Identity: id, name
- Gate behavior: is_user_gate, approve_target, reject_target
- Advancement: validate(), next_phase(), progress_key(), success_message()
"""
import re
from abc import ABC, abstractmethod

from core.phase import phase_key


class Phase(ABC):
    """Abstract base for all workflow phases."""

    @property
    @abstractmethod
    def id(self) -> str:
        """Dotted phase identifier, e.g. '1.2' or '3.1.0'."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable phase name."""

    @property
    def is_user_gate(self) -> bool:
        """Whether this phase requires explicit user approval to proceed."""
        return False

    @property
    def approve_target(self) -> str | None:
        """Phase to transition to on gate approval. Only for gates."""
        return None

    @property
    def reject_target(self) -> str | None:
        """Phase to transition to on gate rejection. Only for gates."""
        return None

    def on_approve(self, ws, body, db):
        """Hook called during gate approval. Override to save data (e.g., commit message)."""
        pass

    @abstractmethod
    def validate(self, ws, body, project_path) -> tuple:
        """Phase-specific validation. Returns (ok: bool, details: dict)."""

    @abstractmethod
    def next_phase(self, ws) -> str:
        """The phase to advance to after successful validation."""

    def progress_key(self, ws) -> str | None:
        """If not None, a progress entry with this key must exist before advancing."""
        return None

    def success_message(self, ws, new_phase) -> str:
        """Message returned on successful advance. Override for custom messages."""
        from core.i18n import t

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
            if guide:
                return t("advance.success.advancedWithGuide", locale, phase=new_phase, guide=guide)
            return t("advance.success.advanced", locale, phase=new_phase)

        guide = phase_guides.get(new_phase, "")
        if guide:
            return t("advance.success.advancedWithGuide", locale, phase=new_phase, guide=guide)
        return t("advance.success.advanced", locale, phase=new_phase)

    def __lt__(self, other):
        a = phase_key(self.id)
        b = phase_key(other.id if isinstance(other, Phase) else str(other))
        return a < b

    def __le__(self, other):
        return self == other or self < other

    def __gt__(self, other):
        a = phase_key(self.id)
        b = phase_key(other.id if isinstance(other, Phase) else str(other))
        return a > b

    def __ge__(self, other):
        return self == other or self > other

    def __eq__(self, other):
        if isinstance(other, Phase):
            return self.id == other.id
        return self.id == str(other)

    def __hash__(self):
        return hash(self.id)

    def __repr__(self):
        return f"{self.__class__.__name__}('{self.id}')"


# Phase registry -- populated by submodule imports below
PHASE_REGISTRY: dict[str, Phase] = {}


def register_phase(phase: Phase):
    """Register a phase instance in the global registry."""
    PHASE_REGISTRY[phase.id] = phase


def get_phase(phase_str: str) -> Phase | None:
    """Look up a Phase by its dotted string ID.

    For execution phases (3.N.K), creates a parameterized instance on demand.
    """
    if phase_str in PHASE_REGISTRY:
        return PHASE_REGISTRY[phase_str]

    # Dynamic execution phases: 3.N.K
    m = re.match(r'^3\.(\d+)\.(\d+)$', phase_str)
    if m:
        from advance.phases.execution import get_execution_phase
        return get_execution_phase(int(m.group(1)), int(m.group(2)))

    return None


# Import and register all static phases
from advance.phases.preparation import PHASES as _prep_phases  # noqa: E402
from advance.phases.planning import PHASES as _plan_phases  # noqa: E402
from advance.phases.finalization import PHASES as _final_phases  # noqa: E402

for _phase in _prep_phases + _plan_phases + _final_phases:
    register_phase(_phase)
