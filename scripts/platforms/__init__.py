"""
Platform abstraction for multi-platform view count boosting.
"""

from .base import Platform
from .bilibili import BilibiliPlatform
from .xiaohongshu import XiaohongshuPlatform

# Platform registry
PLATFORMS = {
    'bilibili': BilibiliPlatform,
    'xiaohongshu': XiaohongshuPlatform,
    'xhs': XiaohongshuPlatform,  # Alias
}


def get_platform(name: str) -> Platform:
    """Get platform instance by name."""
    name_lower = name.lower()
    if name_lower not in PLATFORMS:
        raise ValueError(f'Unknown platform: {name}. Available: {", ".join(PLATFORMS.keys())}')
    return PLATFORMS[name_lower]()


__all__ = ['Platform', 'BilibiliPlatform', 'XiaohongshuPlatform', 'get_platform', 'PLATFORMS']
