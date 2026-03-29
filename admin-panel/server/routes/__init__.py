"""Blueprint registration."""
from .projects import bp as projects_bp
from .workspaces import bp as workspaces_bp
from .state import bp as state_bp
from .comments import bp as comments_bp
from .files import bp as files_bp
from .hooks import bp as hooks_bp
from .hook_api import bp as hook_api_bp
from .context import bp as context_bp
from .criteria import bp as criteria_bp
from .static import bp as static_bp
from .git_config import bp as git_config_bp
from .advance import bp as advance_bp
from .terminal_routes import bp as terminal_bp, register_terminal_ws
from .improvements import bp as improvements_bp
from .verification import bp as verification_bp
from .modules import bp as modules_bp
from .setup import bp as setup_bp, register_setup_ws
from .lsp import bp as lsp_bp, register_lsp_ws


def register_blueprints(app):
    for bp_module in [projects_bp, workspaces_bp, state_bp, comments_bp, files_bp, hooks_bp, hook_api_bp, context_bp, criteria_bp, static_bp, git_config_bp, advance_bp, terminal_bp, improvements_bp, verification_bp, modules_bp, setup_bp, lsp_bp]:
        app.register_blueprint(bp_module)
    register_terminal_ws(app)
    register_setup_ws(app)
    register_lsp_ws(app)
