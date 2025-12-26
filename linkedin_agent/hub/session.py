"""
Session Management - Factory for S3 or File session managers.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from strands.session.file_session_manager import FileSessionManager

from .config import get_config

if TYPE_CHECKING:
    from strands.session.s3_session_manager import S3SessionManager


def create_session_manager(
    agent_id: str,
    run_id: str | None = None,
    use_s3: bool | None = None,
) -> "FileSessionManager | S3SessionManager":
    """
    Create a session manager for an agent.

    Args:
        agent_id: Unique identifier for the agent
        run_id: Optional run ID (defaults to agent_id + timestamp)
        use_s3: Override config USE_S3 setting

    Returns:
        FileSessionManager or S3SessionManager based on config
    """
    config = get_config()

    # Generate run_id if not provided
    if run_id is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_id = f"{agent_id}_{timestamp}"

    # Determine whether to use S3
    should_use_s3 = use_s3 if use_s3 is not None else config.use_s3

    if should_use_s3:
        try:
            from strands.session.s3_session_manager import S3SessionManager

            return S3SessionManager(
                session_id=run_id,
                bucket=config.bucket,
                prefix=config.sessions_prefix,
                region_name=config.region,
            )
        except ImportError:
            print("Warning: S3SessionManager not available, falling back to local")
            should_use_s3 = False
        except Exception as e:
            print(f"Warning: S3 unavailable ({e}), falling back to local")
            should_use_s3 = False

    # Local fallback
    return FileSessionManager(
        session_id=run_id,
        storage_dir=str(config.local_sessions_dir),
    )


def generate_run_id(agent_id: str) -> str:
    """Generate a unique run ID with timestamp."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{agent_id}_{timestamp}"
