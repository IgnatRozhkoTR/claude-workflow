"""Blueprint registration."""
from .projects import bp as projects_bp
from .workspaces import bp as workspaces_bp
from .state import bp as state_bp
from .comments import bp as comments_bp
from .files import bp as files_bp
from .hooks import bp as hooks_bp
from .context import bp as context_bp
from .criteria import bp as criteria_bp
from .static import bp as static_bp
from .git_config import bp as git_config_bp
from .advance import bp as advance_bp


def register_blueprints(app):
    for bp_module in [projects_bp, workspaces_bp, state_bp, comments_bp, files_bp, hooks_bp, context_bp, criteria_bp, static_bp, git_config_bp, advance_bp]:
        app.register_blueprint(bp_module)
