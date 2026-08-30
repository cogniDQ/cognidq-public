"""Connection manager for data sources with credential encryption."""

import logging
import os
from typing import Any

from cryptography.fernet import Fernet

from app.services.datasources.connectors.base import BaseConnector
from app.services.datasources.connectors.csv_connector import CSVConnector
from app.services.datasources.connectors.excel_connector import ExcelConnector
from app.services.datasources.connectors.json_connector import JSONConnector
from app.services.datasources.connectors.parquet_connector import ParquetConnector
from app.services.datasources.connectors.postgresql import PostgreSQLConnector
from app.services.datasources.connectors.s3_connector import S3Connector

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Manages data source connections with credential encryption/decryption.
    """

    # Encryption key (in production, load from environment variable or secrets manager)
    ENCRYPTION_KEY = os.getenv("DATASOURCE_ENCRYPTION_KEY", Fernet.generate_key().decode())

    @classmethod
    def get_cipher(cls) -> Fernet:
        """Get Fernet cipher for encryption/decryption."""
        return Fernet(cls.ENCRYPTION_KEY.encode())

    @classmethod
    def encrypt_config(cls, connection_config: dict[str, Any]) -> dict[str, Any]:
        """
        Encrypt sensitive fields in connection configuration.

        Args:
            connection_config: Plain connection config with credentials

        Returns:
            Connection config with encrypted credentials
        """
        cipher = cls.get_cipher()
        encrypted_config = connection_config.copy()

        # Fields to encrypt
        sensitive_fields = [
            "password",
            "api_key",
            "access_key",
            "secret_key",
            "service_account_key",
        ]

        for field in sensitive_fields:
            if field in encrypted_config and encrypted_config[field]:
                try:
                    plain_text = str(encrypted_config[field])
                    encrypted_text = cipher.encrypt(plain_text.encode()).decode()
                    encrypted_config[field] = f"encrypted:{encrypted_text}"
                except Exception as e:
                    logger.error(f"Failed to encrypt field {field}: {e}")
                    raise

        return encrypted_config

    @classmethod
    def decrypt_config(cls, connection_config: dict[str, Any]) -> dict[str, Any]:
        """
        Decrypt sensitive fields in connection configuration.

        Args:
            connection_config: Connection config with encrypted credentials

        Returns:
            Connection config with decrypted credentials
        """
        cipher = cls.get_cipher()
        decrypted_config = connection_config.copy()

        for key, value in decrypted_config.items():
            if isinstance(value, str) and value.startswith("encrypted:"):
                try:
                    encrypted_text = value.replace("encrypted:", "")
                    decrypted_text = cipher.decrypt(encrypted_text.encode()).decode()
                    decrypted_config[key] = decrypted_text
                except Exception as e:
                    logger.error(f"Failed to decrypt field {key}: {e}")
                    # Provide more helpful error message
                    error_msg = f"Failed to decrypt credential '{key}'. This usually happens when the encryption key has changed. Please re-save the data source credentials."
                    raise ValueError(error_msg) from e

        return decrypted_config

    @classmethod
    def mask_config(cls, connection_config: dict[str, Any]) -> dict[str, Any]:
        """
        Mask sensitive fields for API responses.

        Args:
            connection_config: Connection config

        Returns:
            Connection config with masked credentials
        """
        masked_config = connection_config.copy()

        sensitive_fields = [
            "password",
            "api_key",
            "access_key",
            "secret_key",
            "service_account_key",
        ]

        for field in sensitive_fields:
            if field in masked_config and masked_config[field]:
                masked_config[field] = "********"

        return masked_config

    @classmethod
    async def get_connector(
        cls, datasource_type: str, connection_config: dict[str, Any]
    ) -> BaseConnector:
        """
        Get appropriate connector instance for a data source type.

        Args:
            datasource_type: Type of data source (postgresql, mysql, etc.)
            connection_config: Encrypted connection config

        Returns:
            Connected connector instance
        """
        # Decrypt config before creating connector
        decrypted_config = cls.decrypt_config(connection_config)

        connector_map = {
            "postgresql": PostgreSQLConnector,
            "csv": CSVConnector,
            "excel": ExcelConnector,
            "json": JSONConnector,
            "parquet": ParquetConnector,
            "s3": S3Connector,
            # Add more connectors as they are implemented
            # 'mysql': MySQLConnector,
            # 'snowflake': SnowflakeConnector,
            # 'databricks': DatabricksConnector,
        }

        connector_class = connector_map.get(datasource_type)
        if not connector_class:
            raise ValueError(f"Unsupported data source type: {datasource_type}")

        connector = connector_class(decrypted_config)
        await connector.connect()
        return connector

    @classmethod
    async def test_connection(
        cls, datasource_type: str, connection_config: dict[str, Any], encrypted: bool = False
    ):
        """
        Test connection to a data source.

        Args:
            datasource_type: Type of data source
            connection_config: Connection configuration (encrypted or plain)
            encrypted: Whether config is already encrypted

        Returns:
            Tuple of (success, message, details)
        """
        try:
            # If encrypted, decrypt. If not encrypted, use as-is (don't encrypt then decrypt)
            if encrypted:
                config_to_use = cls.decrypt_config(connection_config)
            else:
                config_to_use = connection_config

            # Create connector with plain config
            connector_map = {
                "postgresql": PostgreSQLConnector,
                "csv": CSVConnector,
                "excel": ExcelConnector,
                "json": JSONConnector,
                "parquet": ParquetConnector,
                "s3": S3Connector,
                # Add more connectors as they are implemented
                # 'mysql': MySQLConnector,
                # 'snowflake': SnowflakeConnector,
                # 'databricks': DatabricksConnector,
            }

            connector_class = connector_map.get(datasource_type)
            if not connector_class:
                raise ValueError(f"Unsupported data source type: {datasource_type}")

            connector = connector_class(config_to_use)
            result = await connector.test_connection()

            return result
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False, f"Connection test failed: {str(e)}", None
