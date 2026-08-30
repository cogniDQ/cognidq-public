"""Base connector interface for data source connections."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar

# ─────────────────────────────────────────────────────────────────────────────
# Error normalisation (spec §13.3 / §13.4)
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class NormalizedConnectorError:
    """Result of :meth:`BaseConnector.normalize_error`.

    ``code`` is one of the codes in
    ``backend/app/services/connections/errors.py`` (spec §13.4). ``message``
    is safe to expose to the UI; it never contains credentials. ``original``
    is the underlying exception, preserved for logging only.
    """

    code: str
    message: str
    original: BaseException | None = None

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


# Substring → error-code map. Order matters: most specific first.
_ERROR_PATTERN_MAP: tuple[tuple[str, str], ...] = (
    ("authentication failed", "CONNECTION_AUTH_FAILED"),
    ("password authentication", "CONNECTION_AUTH_FAILED"),
    ("invalid credentials", "CONNECTION_AUTH_FAILED"),
    ("login failed", "CONNECTION_AUTH_FAILED"),
    ("permission denied", "CONNECTION_PERMISSION_DENIED"),
    ("not authorized", "CONNECTION_PERMISSION_DENIED"),
    ("access denied", "CONNECTION_PERMISSION_DENIED"),
    ("timeout", "CONNECTION_TIMEOUT"),
    ("timed out", "CONNECTION_TIMEOUT"),
    ("could not connect", "CONNECTION_NETWORK_ERROR"),
    ("connection refused", "CONNECTION_NETWORK_ERROR"),
    ("name or service not known", "CONNECTION_NETWORK_ERROR"),
    ("could not translate host name", "CONNECTION_NETWORK_ERROR"),
    ("network is unreachable", "CONNECTION_NETWORK_ERROR"),
    ("ssl", "CONNECTION_INVALID_CONFIG"),
)


class BaseConnector(ABC):
    """
    Abstract base class for data source connectors.
    All connector implementations must inherit from this class.

    The legacy abstract methods (``test_connection``, ``connect``, ...) cover
    the original F004 surface. The spec §10.2 surface (``validate_config``,
    ``discover_*``, ``preview_dataset``, ``execute_check``, ``normalize_error``)
    is provided as concrete defaults so existing subclasses keep working.
    Subclasses override only what their capabilities declare.
    """

    #: Optional canonical registry id (e.g. ``"postgresql"``). When set,
    #: :meth:`validate_config` looks up the credential schema from the
    #: registry and validates ``connection_config`` against it.
    connector_type: ClassVar[str | None] = None

    def __init__(self, connection_config: dict[str, Any]):
        """
        Initialize connector with connection configuration.

        Args:
            connection_config: Dictionary containing connection parameters
        """
        self.connection_config = connection_config
        self.connection = None

    @abstractmethod
    async def test_connection(self) -> tuple[bool, str, dict[str, Any] | None]:
        """
        Test the connection to the data source.

        Returns:
            Tuple of (success: bool, message: str, details: Optional[Dict])
        """
        pass

    @abstractmethod
    async def connect(self):
        """
        Establish connection to the data source.
        Should set self.connection to the active connection object.
        """
        pass

    @abstractmethod
    async def disconnect(self):
        """Close the connection to the data source."""
        pass

    @abstractmethod
    async def get_schemas(self) -> list[str]:
        """
        Get list of available schemas/databases.

        Returns:
            List of schema names
        """
        pass

    @abstractmethod
    async def get_tables(self, schema_name: str | None = None) -> list[dict[str, Any]]:
        """
        Get list of tables in a schema.

        Args:
            schema_name: Schema name (optional, uses default if None)

        Returns:
            List of dictionaries with table metadata
            [{
                "schema_name": str,
                "table_name": str,
                "row_count": int (optional)
            }]
        """
        pass

    @abstractmethod
    async def get_columns(
        self, table_name: str, schema_name: str | None = None
    ) -> list[dict[str, Any]]:
        """
        Get column metadata for a table.

        Args:
            table_name: Table name
            schema_name: Schema name (optional, uses default if None)

        Returns:
            List of dictionaries with column metadata
            [{
                "column_name": str,
                "column_type": str,
                "is_nullable": bool,
                "is_primary_key": bool,
                "default_value": str (optional),
                "metadata": dict (optional - max_length, precision, scale, etc.)
            }]
        """
        pass

    @abstractmethod
    async def execute_query(
        self, query: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """
        Execute a SQL query and return results.

        Args:
            query: SQL query string
            params: Query parameters (optional)

        Returns:
            List of dictionaries representing rows
        """
        pass

    @abstractmethod
    async def get_row_count(self, table_name: str, schema_name: str | None = None) -> int:
        """
        Get row count for a table.

        Args:
            table_name: Table name
            schema_name: Schema name (optional)

        Returns:
            Number of rows in the table
        """
        pass

    async def get_sample_data(
        self, table_name: str, schema_name: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        """
        Get sample data from a table.

        Args:
            table_name: Table name
            schema_name: Schema name (optional)
            limit: Number of rows to retrieve

        Returns:
            List of dictionaries representing sample rows
        """
        full_table_name = f'"{schema_name}"."{table_name}"' if schema_name else f'"{table_name}"'
        query = f"SELECT * FROM {full_table_name} LIMIT {limit}"
        return await self.execute_query(query)

    # ─────────────────────────────────────────────────────────────────────
    # Spec §10.2 surface — concrete defaults; override per connector.
    # ─────────────────────────────────────────────────────────────────────

    def validate_config(self) -> list[dict[str, str]]:
        """Validate ``self.connection_config`` against the credential schema.

        Looks up the credential schema in the connector registry using
        :attr:`connector_type`. Returns a list of field-error dicts (empty
        when valid). Subclasses may override for richer rules (e.g. URL parse
        checks, mutually exclusive fields).

        Returns:
            List of ``{"field": <name>, "message": <reason>}`` entries.
            Empty list means the config is valid.
        """
        # Lazy import to avoid a circular import at module load time.
        from app.services.datasources.connectors.registry import (
            registry as _registry,
        )

        errors: list[dict[str, str]] = []
        if not self.connector_type:
            return errors

        spec = _registry.get(self.connector_type)
        if spec is None:
            return errors

        cfg = self.connection_config or {}
        for field in spec.credential_schema:
            value = cfg.get(field.name)
            if field.required and (value is None or value == ""):
                errors.append(
                    {
                        "field": field.name,
                        "message": f"{field.label} is required.",
                    }
                )
        return errors

    async def discover_schemas(self) -> list[str]:
        """Default: delegate to :meth:`get_schemas` (legacy)."""
        return await self.get_schemas()

    async def discover_tables(self, schema_name: str | None = None) -> list[dict[str, Any]]:
        """Default: delegate to :meth:`get_tables` (legacy)."""
        return await self.get_tables(schema_name=schema_name)

    async def discover_files(self, path: str | None = None) -> list[dict[str, Any]]:
        """File / object-storage discovery. Override in file-based connectors."""
        raise NotImplementedError(f"{type(self).__name__} does not support file discovery")

    async def discover_assets(self, schema_name: str | None = None) -> dict[str, Any]:
        """Aggregate discovery surface (spec §10.2).

        Tries schemas/tables (databases, warehouses, lakehouses) and falls
        back to files (object storage / file connectors). Returns whichever
        the connector supports; missing surfaces are simply absent from the
        result.
        """
        result: dict[str, Any] = {}
        try:
            result["schemas"] = await self.discover_schemas()
        except NotImplementedError:
            pass
        try:
            result["tables"] = await self.discover_tables(schema_name=schema_name)
        except NotImplementedError:
            pass
        try:
            result["files"] = await self.discover_files()
        except NotImplementedError:
            pass
        return result

    async def preview_dataset(
        self,
        table_name: str,
        schema_name: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Default: delegate to :meth:`get_sample_data`."""
        return await self.get_sample_data(
            table_name=table_name, schema_name=schema_name, limit=limit
        )

    def register_dataset(self, *args: Any, **kwargs: Any) -> Any:
        """Stub. Dataset registration is handled by the dataset service.

        Connectors that need to do anything custom at registration time
        (e.g. record an external bookmark) override this.
        """
        raise NotImplementedError(f"{type(self).__name__} does not implement register_dataset")

    async def execute_check(self, *args: Any, **kwargs: Any) -> Any:
        """Stub. Wired up per-connector when DQ checks are pushed down."""
        raise NotImplementedError(f"{type(self).__name__} does not implement execute_check")

    def normalize_error(self, exc: BaseException) -> NormalizedConnectorError:
        """Map an arbitrary exception to a spec §13.4 error code.

        The mapping is conservative: anything that doesn't match a known
        pattern is reported as ``CONNECTION_INVALID_CONFIG`` so the caller
        gets a structured response instead of a 500.

        SECURITY: ``self.connection_config`` is **never** included in the
        returned ``message``; only the exception's own string form is used,
        and it is truncated to 500 chars.
        """
        raw = str(exc) or type(exc).__name__
        lowered = raw.lower()
        code = "CONNECTION_INVALID_CONFIG"
        for needle, mapped in _ERROR_PATTERN_MAP:
            if needle in lowered:
                code = mapped
                break
        return NormalizedConnectorError(
            code=code,
            message=raw[:500],
            original=exc,
        )

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()
