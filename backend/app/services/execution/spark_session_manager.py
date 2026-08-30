"""
Spark Session Manager
Singleton manager for Spark session lifecycle across all check executions.
"""

import logging
import os
import threading
from typing import Optional

from pyspark.sql import SparkSession

logger = logging.getLogger(__name__)


class SparkSessionManager:
    """
    Singleton manager for Spark session lifecycle.

    Manages shared Spark session across all check executions to avoid
    overhead of creating new sessions for each check.
    """

    _instance: Optional["SparkSessionManager"] = None
    _lock = threading.Lock()
    _session: SparkSession | None = None
    _session_lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def get_instance(cls) -> "SparkSessionManager":
        """Get singleton instance"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_session(self) -> SparkSession:
        """
        Get or create shared Spark session.

        Session is created once and reused across all checks.
        Configuration is loaded from environment variables.

        Returns:
            SparkSession instance
        """
        if self._session is None or self._is_session_stopped():
            with self._session_lock:
                if self._session is None or self._is_session_stopped():
                    logger.info("Creating new Spark session")
                    self._session = self._create_session()
        return self._session

    def _is_session_stopped(self) -> bool:
        """Check if session has been stopped"""
        if self._session is None:
            return True
        try:
            # Try to access the SparkContext - will fail if stopped
            _ = self._session.sparkContext.version
            return False
        except Exception:
            return True

    def _create_session(self) -> SparkSession:
        """Create new Spark session with configuration"""
        import sys

        deployment_mode = os.getenv("DEPLOYMENT_MODE", "docker-compose")
        master_url = os.getenv("SPARK_MASTER_URL", "local[*]")
        driver_memory = os.getenv("SPARK_DRIVER_MEMORY", "2g")
        executor_memory = os.getenv("SPARK_EXECUTOR_MEMORY", "4g")
        executor_cores = os.getenv("SPARK_EXECUTOR_CORES", "2")

        logger.info(f"Initializing Spark session - Mode: {deployment_mode}, Master: {master_url}")

        # Fix Python version mismatch between driver and workers
        # Get the Python executable being used by driver
        python_executable = sys.executable
        logger.info(f"Python executable: {python_executable}")
        logger.info(f"Python version: {sys.version}")

        # Set environment variables to ensure workers use same Python version
        # Use environment variables if set, otherwise use driver's Python
        pyspark_python = os.getenv("PYSPARK_PYTHON", python_executable)
        pyspark_driver_python = os.getenv("PYSPARK_DRIVER_PYTHON", python_executable)

        # Override with explicit path for cluster mode to ensure consistency
        if master_url.startswith("spark://"):
            # Cluster mode - use Python 3.11 (matching our custom worker images)
            pyspark_python = "/usr/local/bin/python3.11"
            pyspark_driver_python = "/usr/local/bin/python3.11"

        os.environ["PYSPARK_PYTHON"] = pyspark_python
        os.environ["PYSPARK_DRIVER_PYTHON"] = pyspark_driver_python
        logger.info(f"Set PYSPARK_PYTHON={pyspark_python}")
        logger.info(f"Set PYSPARK_DRIVER_PYTHON={pyspark_driver_python}")

        # Create event log directory if it doesn't exist
        event_log_dir = "/tmp/spark-events"
        try:
            import pathlib

            pathlib.Path(event_log_dir).mkdir(parents=True, exist_ok=True)
            logger.info(f"✅ Event log directory ensured: {event_log_dir}")
        except Exception as e:
            logger.warning(f"⚠️ Could not create event log directory {event_log_dir}: {e}")
            logger.warning("   Disabling event logging")
            event_log_dir = None

        builder = (
            SparkSession.builder.appName("DataQuality_SaaS_Checks")
            .master(master_url)
            .config("spark.driver.memory", driver_memory)
            .config("spark.executor.memory", executor_memory)
            .config("spark.executor.cores", executor_cores)
            # Adaptive query execution
            .config("spark.sql.adaptive.enabled", "true")
            .config("spark.sql.adaptive.coalescePartitions.enabled", "true")
            # Dynamic allocation (if enabled)
            .config(
                "spark.dynamicAllocation.enabled",
                os.getenv("SPARK_DYNAMIC_ALLOCATION_ENABLED", "false"),
            )
            .config(
                "spark.shuffle.service.enabled", os.getenv("SPARK_SHUFFLE_SERVICE_ENABLED", "false")
            )
            # Security - disable authentication for now since Spark master doesn't have it enabled
            # In production, both client and master should use authentication with matching secret
            .config("spark.authenticate", "false")
            .config("spark.network.crypto.enabled", "false")
            # Python executable configuration - ensure workers use same Python version
            .config("spark.pyspark.python", pyspark_python)
            .config("spark.pyspark.driver.python", pyspark_driver_python)
        )

        # Add event logging config only if directory was created successfully
        if event_log_dir:
            builder = (
                builder.config("spark.eventLog.enabled", "true")
                .config("spark.eventLog.dir", event_log_dir)
                .config("spark.eventLog.logStageExecutorMetrics", "true")
                .config("spark.eventLog.buffer.kb", "100")
            )

        # Continue with other configs
        builder = (
            builder
            # Keep UI alive longer after job completion
            .config("spark.ui.retainedJobs", "1000")
            .config("spark.ui.retainedStages", "1000")
            .config("spark.worker.ui.retainedExecutors", "100")
            .config("spark.worker.ui.retainedDrivers", "100")
            .config("spark.sql.ui.retainedExecutions", "1000")
            # Prevent executor timeout and premature cleanup
            .config("spark.executor.heartbeatInterval", "20s")
            .config("spark.network.timeout", "800s")
            .config("spark.storage.blockManagerSlaveTimeoutMs", "600000")
        )

        # Add JDBC packages for database connectivity
        packages = self._get_jdbc_packages()
        if packages:
            builder = builder.config("spark.jars.packages", packages)

        # Cloud-specific configurations
        if "aws" in deployment_mode.lower():
            builder = self._configure_aws(builder)
        elif "azure" in deployment_mode.lower():
            builder = self._configure_azure(builder)
        elif "gcp" in deployment_mode.lower():
            builder = self._configure_gcp(builder)

        session = builder.getOrCreate()

        # Set log level
        session.sparkContext.setLogLevel("WARN")

        logger.info(f"Spark session created successfully - Version: {session.version}")
        return session

    def _get_jdbc_packages(self) -> str:
        """Get required JDBC packages based on supported data sources"""
        packages = [
            "org.postgresql:postgresql:42.7.1",
            "com.mysql:mysql-connector-j:8.2.0",
            "net.snowflake:snowflake-jdbc:3.14.4",
            "net.snowflake:spark-snowflake_2.12:2.12.0-spark_3.4",
        ]
        return ",".join(packages)

    def _configure_aws(self, builder: SparkSession.Builder) -> SparkSession.Builder:
        """Configure Spark for AWS deployment"""
        logger.info("Configuring Spark for AWS")

        # AWS specific configs
        aws_region = os.getenv("AWS_REGION", "us-east-1")

        return (
            builder.config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
            .config(
                "spark.hadoop.fs.s3a.aws.credentials.provider",
                "com.amazonaws.auth.DefaultAWSCredentialsProviderChain",
            )
            .config("spark.hadoop.fs.s3a.endpoint", f"s3.{aws_region}.amazonaws.com")
        )

    def _configure_azure(self, builder: SparkSession.Builder) -> SparkSession.Builder:
        """Configure Spark for Azure deployment"""
        logger.info("Configuring Spark for Azure")

        # Azure specific configs
        storage_account = os.getenv("AZURE_STORAGE_ACCOUNT", "")

        if storage_account:
            return builder.config(
                f"spark.hadoop.fs.azure.account.auth.type.{storage_account}.dfs.core.windows.net",
                "OAuth",
            ).config(
                f"spark.hadoop.fs.azure.account.oauth.provider.type.{storage_account}.dfs.core.windows.net",
                "org.apache.hadoop.fs.azurebfs.oauth2.ClientCredsTokenProvider",
            )

        return builder

    def _configure_gcp(self, builder: SparkSession.Builder) -> SparkSession.Builder:
        """Configure Spark for GCP deployment"""
        logger.info("Configuring Spark for GCP")

        # GCP specific configs
        gcp_project = os.getenv("GCP_PROJECT_ID", "")

        return builder.config(
            "spark.hadoop.google.cloud.auth.service.account.enable", "true"
        ).config("spark.hadoop.fs.gs.project.id", gcp_project)

    def close_session(self):
        """Close Spark session (called on application shutdown)"""
        if self._session is not None:
            with self._session_lock:
                if self._session is not None:
                    try:
                        logger.info("Closing Spark session")
                        self._session.stop()
                        logger.info("Spark session closed successfully")
                    except Exception as e:
                        logger.error(f"Error closing Spark session: {e}")
                    finally:
                        self._session = None

    def restart_session(self) -> SparkSession:
        """Restart Spark session (useful for configuration changes)"""
        logger.info("Restarting Spark session")
        self.close_session()
        return self.get_session()

    def get_session_info(self) -> dict:
        """Get information about current Spark session"""
        if self._session is None or self._is_session_stopped():
            return {"status": "stopped", "session_active": False}

        try:
            sc = self._session.sparkContext
            return {
                "status": "active",
                "session_active": True,
                "app_name": sc.appName,
                "master": sc.master,
                "spark_version": sc.version,
                "spark_user": sc.sparkUser(),
                "default_parallelism": sc.defaultParallelism,
            }
        except Exception as e:
            logger.error(f"Error getting session info: {e}")
            return {"status": "error", "session_active": False, "error": str(e)}
