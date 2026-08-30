"""
F134 P06 — Template Seeder Service

Loads a demo template's seeder by the `seeder_module` path recorded in
control.demo_templates and invokes it for a given tenant/workspace.
"""

from __future__ import annotations

import importlib
import logging
from uuid import UUID

from sqlalchemy.orm import Session

from app.services.sandbox.demo_template_repository import DemoTemplateRepository

logger = logging.getLogger(__name__)


class SeedingError(RuntimeError):
    """Raised when a template seeder fails unrecoverably."""


class TemplateSeederService:
    """Loads and runs the seeder module for a given template_id."""

    def __init__(
        self,
        db: Session,
        template_repo: DemoTemplateRepository | None = None,
    ) -> None:
        self._db = db
        self._template_repo = template_repo or DemoTemplateRepository(db)

    def seed(
        self,
        template_id: str,
        tenant_id: UUID,
        workspace_id: UUID,
    ) -> None:
        """
        Look up the seeder module for ``template_id``, instantiate it, and
        call ``seed(tenant_id, workspace_id)``.

        Raises:
            SeedingError: if the template does not exist, the module cannot
                be imported, or the seeder raises an unexpected exception.
        """
        template_row = self._template_repo.find_by_id(template_id)
        if template_row is None:
            raise SeedingError(f"Demo template '{template_id}' not found.")

        module_path: str = template_row["seeder_module"]
        if not module_path:
            raise SeedingError(f"Demo template '{template_id}' has no seeder_module configured.")

        try:
            module = importlib.import_module(module_path)
        except ImportError as exc:
            raise SeedingError(f"Cannot import seeder module '{module_path}': {exc}") from exc

        # Convention: the module exposes a class named after its template_id
        # in PascalCase + "Seeder" suffix, e.g. GeneralDQSeeder for general_dq.
        # Fall back to a ``create_seeder(db)`` factory function if present.
        seeder = _instantiate_seeder(module, module_path, self._db)

        try:
            seeder.seed(tenant_id, workspace_id)
        except SeedingError:
            raise
        except Exception as exc:
            logger.exception("Seeder for template '%s' raised an unexpected error.", template_id)
            raise SeedingError(f"Seeder for template '{template_id}' failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _instantiate_seeder(module, module_path: str, db: Session):
    """
    Locate the seeder class or factory in the module.

    Resolution order:
    1. ``module.create_seeder(db)`` factory function
    2. Any class that exposes a ``seed`` method and a ``template_id`` attribute
    """
    if hasattr(module, "create_seeder") and callable(module.create_seeder):
        return module.create_seeder(db)

    # Walk module attributes looking for a seeder class
    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        if isinstance(attr, type) and hasattr(attr, "seed") and hasattr(attr, "template_id"):
            return attr(db)

    raise SeedingError(
        f"Seeder module '{module_path}' does not expose a seeder class or create_seeder() factory."
    )
