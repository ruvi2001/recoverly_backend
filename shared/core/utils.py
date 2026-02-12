"""
Common utility functions shared across all services
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import logging


def setup_logging(service_name: str, log_level: str = "INFO") -> logging.Logger:
    """
    Set up logging for a service
    
    Args:
        service_name: Name of the service
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(service_name)
    logger.setLevel(getattr(logging, log_level.upper()))
    
    # Console handler
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        f'%(asctime)s - {service_name} - %(levelname)s - %(message)s'
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    
    return logger


def calculate_days_ago(timestamp: datetime) -> int:
    """Calculate how many days ago a timestamp was"""
    if timestamp is None:
        return -1
    return (datetime.now() - timestamp).days


def format_timestamp(dt: Optional[datetime]) -> Optional[str]:
    """Format datetime to ISO string"""
    return dt.isoformat() if dt else None


def parse_timestamp(timestamp_str: Optional[str]) -> Optional[datetime]:
    """Parse ISO timestamp string to datetime"""
    if not timestamp_str:
        return None
    try:
        return datetime.fromisoformat(timestamp_str)
    except (ValueError, TypeError):
        return None


def get_time_window_start(days: int) -> datetime:
    """Get the start datetime for a time window"""
    return datetime.now() - timedelta(days=days)


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Safely divide two numbers, returning default if denominator is zero"""
    return numerator / denominator if denominator != 0 else default


def truncate_text(text: str, max_length: int = 100) -> str:
    """Truncate text to maximum length"""
    return text[:max_length] + "..." if len(text) > max_length else text
