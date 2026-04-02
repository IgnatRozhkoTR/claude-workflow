"""MCP stdio server — governed workflow admin panel.

All tool implementations live in mcp_tools/.
Importing mcp_tools triggers @mcp.tool registration for all 32 tools.
"""
from mcp_tools import mcp
from mcp_tools.state import workspace_get_state
from mcp_tools.advance import workspace_advance
from mcp_tools.plan_scope import (
    workspace_set_scope,
    workspace_set_plan,
    workspace_get_plan,
    workspace_extend_plan,
    workspace_restore_plan,
)
from mcp_tools.research import (
    workspace_post_discussion,
    workspace_save_research,
    workspace_list_research,
    workspace_get_research,
    workspace_prove_research,
)
from mcp_tools.comments import (
    workspace_get_comments,
    workspace_post_comment,
    workspace_resolve_comment,
    workspace_submit_review_issue,
    workspace_get_review_issues,
    workspace_resolve_review_issue,
)
from mcp_tools.progress import (
    workspace_set_impact_analysis,
    workspace_update_progress,
    workspace_get_progress,
)
from mcp_tools.criteria import (
    workspace_propose_criteria,
    workspace_get_criteria,
    workspace_update_criteria,
)
from mcp_tools.verification import (
    workspace_get_verification_results,
    workspace_get_verification_profiles,
    workspace_create_verification_profile,
    workspace_update_verification_profile,
    workspace_add_verification_step,
    workspace_assign_verification_profile,
    workspace_submit_validation,
)

if __name__ == "__main__":
    mcp.run(transport="stdio")
