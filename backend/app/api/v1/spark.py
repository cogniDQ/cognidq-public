"""
Spark monitoring API endpoints
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.models.user import User
from app.services.auth.jwt import get_current_user
from app.services.execution.spark_session_manager import SparkSessionManager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/spark/status")
async def get_spark_status(current_user: User = Depends(get_current_user)) -> dict[str, Any]:
    """
    Get Spark session status and information.

    Returns:
        Dictionary with Spark session details
    """
    try:
        spark_manager = SparkSessionManager.get_instance()
        session_info = spark_manager.get_session_info()

        return {"success": True, "data": session_info}
    except Exception as e:
        logger.error(f"Error getting Spark status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/spark/restart")
async def restart_spark_session(current_user: User = Depends(get_current_user)) -> dict[str, Any]:
    """
    Restart Spark session (admin only).
    Useful when configuration changes require session restart.

    Returns:
        New session information
    """
    # TODO: Add admin role check
    try:
        spark_manager = SparkSessionManager.get_instance()
        spark_manager.restart_session()
        session_info = spark_manager.get_session_info()

        logger.info(f"Spark session restarted by user {current_user.email}")

        return {
            "success": True,
            "message": "Spark session restarted successfully",
            "data": session_info,
        }
    except Exception as e:
        logger.error(f"Error restarting Spark session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/spark/config")
async def get_spark_config(current_user: User = Depends(get_current_user)) -> dict[str, Any]:
    """
    Get current Spark configuration from environment.

    Returns:
        Dictionary with Spark configuration
    """
    import os

    try:
        config = {
            "deployment_mode": os.getenv("DEPLOYMENT_MODE", "docker-compose"),
            "spark_master_url": os.getenv("SPARK_MASTER_URL", "local[*]"),
            "spark_driver_memory": os.getenv("SPARK_DRIVER_MEMORY", "2g"),
            "spark_executor_memory": os.getenv("SPARK_EXECUTOR_MEMORY", "4g"),
            "spark_executor_cores": os.getenv("SPARK_EXECUTOR_CORES", "2"),
            "spark_auto_threshold": int(os.getenv("SPARK_AUTO_THRESHOLD", "50000")),
            "spark_force_threshold": int(os.getenv("SPARK_FORCE_THRESHOLD", "500000")),
            "enable_cluster_mode": os.getenv("ENABLE_CLUSTER_MODE", "false").lower() == "true",
            "dynamic_allocation_enabled": os.getenv(
                "SPARK_DYNAMIC_ALLOCATION_ENABLED", "false"
            ).lower()
            == "true",
        }

        return {"success": True, "data": config}
    except Exception as e:
        logger.error(f"Error getting Spark config: {e}")
        raise HTTPException(status_code=500, detail=str(e))
