"""
Common utility functions for bilibili-viewcount-booster
"""

import os
from pathlib import Path


def load_env_file(filepath='.env'):
    """
    Load environment variables from .env file

    Args:
        filepath: Path to .env file (default: '.env')

    Returns:
        dict: Dictionary of environment variables from file
    """
    if not os.path.exists(filepath):
        return {}

    env_vars = {}
    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                env_vars[key.strip()] = value.strip().strip('"').strip("'")
    return env_vars


def load_env():
    """Load environment variables from .env file into os.environ"""
    env_file = Path('.env')
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()


def get_env(key, default=None, env_file_vars=None):
    """
    Get configuration value with priority: ENV > .env file > default

    Args:
        key: Environment variable name
        default: Default value if not found
        env_file_vars: Pre-loaded .env file variables (optional)

    Returns:
        Configuration value
    """
    if env_file_vars is None:
        env_file_vars = {}
    return os.getenv(key) or env_file_vars.get(key) or default


def time_format(seconds: int) -> str:
    """
    Format seconds into readable time string

    Args:
        seconds: Number of seconds

    Returns:
        Formatted time string (e.g. "1min 30s" or "45s")
    """
    if seconds < 60:
        return f'{seconds}s'
    else:
        return f'{int(seconds / 60)}min {seconds % 60}s'
