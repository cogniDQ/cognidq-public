"""
Root conftest — ensures all SQLAlchemy models are imported before any test
runs, so relationship names resolve correctly during mapper initialization.
"""

import app.models.access_token  # noqa: F401
import app.models.dashboard  # noqa: F401
import app.models.datasource  # noqa: F401
import app.models.domain  # noqa: F401
import app.models.flow  # noqa: F401
import app.models.nl_rule  # noqa: F401
import app.models.rbac  # noqa: F401
import app.models.rule  # noqa: F401
import app.models.rule_template  # noqa: F401
import app.models.team  # noqa: F401
import app.models.user  # noqa: F401
