"""
Credential Manager for Client Data Sources
Manages secure storage and retrieval of client database credentials.
"""

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


class CredentialManager:
    """
    Manage encrypted client credentials for data source connections.
    Supports multiple backends: environment variables, Kubernetes secrets,
    cloud secret managers (AWS Secrets Manager, Azure Key Vault, GCP Secret Manager).
    """

    def __init__(self):
        self.deployment_mode = os.getenv("DEPLOYMENT_MODE", "docker-compose")
        self.backend = self._initialize_backend()

    def _initialize_backend(self) -> Any | None:
        """Initialize appropriate secret backend based on deployment mode"""

        if "aws" in self.deployment_mode.lower():
            try:
                import boto3

                self.backend_type = "aws"
                return boto3.client(
                    "secretsmanager", region_name=os.getenv("AWS_REGION", "us-east-1")
                )
            except ImportError:
                logger.warning("boto3 not installed, falling back to environment variables")
                self.backend_type = "env"
                return None

        elif "azure" in self.deployment_mode.lower():
            try:
                from azure.identity import DefaultAzureCredential
                from azure.keyvault.secrets import SecretClient

                vault_url = os.getenv("AZURE_KEYVAULT_URL")
                if vault_url:
                    self.backend_type = "azure"
                    return SecretClient(vault_url=vault_url, credential=DefaultAzureCredential())
                else:
                    logger.warning(
                        "AZURE_KEYVAULT_URL not set, falling back to environment variables"
                    )
                    self.backend_type = "env"
                    return None
            except ImportError:
                logger.warning("Azure SDK not installed, falling back to environment variables")
                self.backend_type = "env"
                return None

        elif "gcp" in self.deployment_mode.lower():
            try:
                from google.cloud import secretmanager

                self.backend_type = "gcp"
                return secretmanager.SecretManagerServiceClient()
            except ImportError:
                logger.warning("GCP SDK not installed, falling back to environment variables")
                self.backend_type = "env"
                return None

        # Default to environment variables
        self.backend_type = "env"
        return None

    def get_datasource_credentials(self, datasource_id: str) -> dict[str, Any] | None:
        """
        Retrieve credentials for a data source.

        Args:
            datasource_id: Unique identifier for the data source

        Returns:
            Dictionary with credential information or None
        """
        secret_name = f"datasource-{datasource_id}"

        try:
            if self.backend_type == "aws":
                return self._get_from_aws(secret_name)
            elif self.backend_type == "azure":
                return self._get_from_azure(secret_name)
            elif self.backend_type == "gcp":
                return self._get_from_gcp(secret_name)
            else:
                return self._get_from_env(secret_name)
        except Exception as e:
            logger.error(f"Failed to retrieve credentials for {datasource_id}: {e}")
            return None

    def _get_from_env(self, secret_name: str) -> dict[str, Any] | None:
        """Get credentials from environment variable"""
        env_var = f"DATASOURCE_CREDS_{secret_name.upper().replace('-', '_')}"
        creds_json = os.getenv(env_var)

        if creds_json:
            try:
                return json.loads(creds_json)
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON in {env_var}")
                return None

        return None

    def _get_from_aws(self, secret_name: str) -> dict[str, Any] | None:
        """Get credentials from AWS Secrets Manager"""
        try:
            response = self.backend.get_secret_value(SecretId=secret_name)
            secret_string = response.get("SecretString")

            if secret_string:
                return json.loads(secret_string)

            return None
        except Exception as e:
            logger.error(f"AWS Secrets Manager error: {e}")
            return None

    def _get_from_azure(self, secret_name: str) -> dict[str, Any] | None:
        """Get credentials from Azure Key Vault"""
        try:
            secret = self.backend.get_secret(secret_name)
            return json.loads(secret.value)
        except Exception as e:
            logger.error(f"Azure Key Vault error: {e}")
            return None

    def _get_from_gcp(self, secret_name: str) -> dict[str, Any] | None:
        """Get credentials from GCP Secret Manager"""
        try:
            project_id = os.getenv("GCP_PROJECT_ID")
            name = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
            response = self.backend.access_secret_version(request={"name": name})
            secret_string = response.payload.data.decode("UTF-8")
            return json.loads(secret_string)
        except Exception as e:
            logger.error(f"GCP Secret Manager error: {e}")
            return None

    def store_datasource_credentials(self, datasource_id: str, credentials: dict[str, Any]) -> bool:
        """
        Store credentials for a data source.

        Args:
            datasource_id: Unique identifier for the data source
            credentials: Dictionary with credential information

        Returns:
            True if successful, False otherwise
        """
        secret_name = f"datasource-{datasource_id}"
        creds_json = json.dumps(credentials)

        try:
            if self.backend_type == "aws":
                return self._store_to_aws(secret_name, creds_json)
            elif self.backend_type == "azure":
                return self._store_to_azure(secret_name, creds_json)
            elif self.backend_type == "gcp":
                return self._store_to_gcp(secret_name, creds_json)
            else:
                logger.warning(
                    f"Environment variable backend does not support storing credentials. "
                    f"Manually set {secret_name} in environment."
                )
                return False
        except Exception as e:
            logger.error(f"Failed to store credentials for {datasource_id}: {e}")
            return False

    def _store_to_aws(self, secret_name: str, secret_value: str) -> bool:
        """Store credentials to AWS Secrets Manager"""
        try:
            # Try to update existing secret
            try:
                self.backend.update_secret(SecretId=secret_name, SecretString=secret_value)
            except self.backend.exceptions.ResourceNotFoundException:
                # Create new secret if it doesn't exist
                self.backend.create_secret(Name=secret_name, SecretString=secret_value)

            logger.info(f"Stored credentials to AWS Secrets Manager: {secret_name}")
            return True
        except Exception as e:
            logger.error(f"AWS Secrets Manager store error: {e}")
            return False

    def _store_to_azure(self, secret_name: str, secret_value: str) -> bool:
        """Store credentials to Azure Key Vault"""
        try:
            self.backend.set_secret(secret_name, secret_value)
            logger.info(f"Stored credentials to Azure Key Vault: {secret_name}")
            return True
        except Exception as e:
            logger.error(f"Azure Key Vault store error: {e}")
            return False

    def _store_to_gcp(self, secret_name: str, secret_value: str) -> bool:
        """Store credentials to GCP Secret Manager"""
        try:
            project_id = os.getenv("GCP_PROJECT_ID")
            parent = f"projects/{project_id}"

            # Create secret if it doesn't exist
            try:
                self.backend.create_secret(
                    request={
                        "parent": parent,
                        "secret_id": secret_name,
                        "secret": {"replication": {"automatic": {}}},
                    }
                )
            except Exception:
                pass  # Secret already exists

            # Add new version
            parent_secret = f"{parent}/secrets/{secret_name}"
            self.backend.add_secret_version(
                request={"parent": parent_secret, "payload": {"data": secret_value.encode("UTF-8")}}
            )

            logger.info(f"Stored credentials to GCP Secret Manager: {secret_name}")
            return True
        except Exception as e:
            logger.error(f"GCP Secret Manager store error: {e}")
            return False

    def delete_datasource_credentials(self, datasource_id: str) -> bool:
        """
        Delete credentials for a data source.

        Args:
            datasource_id: Unique identifier for the data source

        Returns:
            True if successful, False otherwise
        """
        secret_name = f"datasource-{datasource_id}"

        try:
            if self.backend_type == "aws":
                self.backend.delete_secret(SecretId=secret_name, ForceDeleteWithoutRecovery=True)
            elif self.backend_type == "azure":
                self.backend.begin_delete_secret(secret_name)
            elif self.backend_type == "gcp":
                project_id = os.getenv("GCP_PROJECT_ID")
                name = f"projects/{project_id}/secrets/{secret_name}"
                self.backend.delete_secret(request={"name": name})
            else:
                logger.warning("Environment variable backend does not support deleting credentials")
                return False

            logger.info(f"Deleted credentials: {secret_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete credentials for {datasource_id}: {e}")
            return False
