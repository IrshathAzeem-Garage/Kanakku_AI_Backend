import logging
import sys

# Configure standard structured logger
logger = logging.getLogger("kanakku-ai")
logger.setLevel(logging.INFO)

if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [KANAKKU-AI] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)


def log_image_analysis(
    request_id: str,
    user_id: int | None,
    original_filename: str,
    image_id: str,
    file_size_bytes: int,
    content_type: str,
    sha256_hash: str,
    analysis_started_at: str,
    analysis_completed_at: str,
    status: str = "SUCCESS",
    duration_ms: float = 0.0,
    extra_info: str = ""
):
    """
    Structured logger for every image analysis request.
    Strictly avoids logging passwords, JWT tokens, or credentials.
    """
    logger.info(
        f"\n[ANALYZE]\n"
        f"request_id={request_id}\n"
        f"user_id={user_id}\n"
        f"original_filename={original_filename}\n"
        f"generated_image_id={image_id}\n"
        f"file_size={file_size_bytes}\n"
        f"content_type={content_type}\n"
        f"sha256={sha256_hash}\n"
        f"analysis_started_at={analysis_started_at}\n"
        f"analysis_completed_at={analysis_completed_at}\n"
        f"status={status}\n"
        f"duration_ms={duration_ms:.1f}"
        f"{f'\ninfo={extra_info}' if extra_info else ''}"
    )

