"""
Base platform interface for view count boosting.
"""

from abc import ABC, abstractmethod
from typing import Any


class Platform(ABC):
    """Abstract base class for platform implementations."""

    @abstractmethod
    def get_name(self) -> str:
        """Get platform name."""
        pass

    @abstractmethod
    def get_video_info(self, video_id: str) -> dict[str, Any]:
        """
        Fetch video information from platform.

        Args:
            video_id: Platform-specific video identifier

        Returns:
            Dictionary with video info including view count

        Raises:
            Exception: If video info cannot be fetched
        """
        pass

    @abstractmethod
    def boost_view(self, video_id: str, info_dict: dict, proxy: str, timeout: int = 5) -> bool:
        """
        Send a view boost request through proxy.

        Args:
            video_id: Platform-specific video identifier
            info_dict: Video information dict from get_video_info()
            proxy: Proxy address (format: ip:port)
            timeout: Request timeout in seconds

        Returns:
            True if request succeeded, False otherwise
        """
        pass

    @abstractmethod
    def get_current_views(self, video_id: str) -> int:
        """
        Get current view count for a video.

        Args:
            video_id: Platform-specific video identifier

        Returns:
            Current view count

        Raises:
            Exception: If view count cannot be fetched
        """
        pass

    @abstractmethod
    def get_user_videos(self, user_id: str, cookies_file: str = None) -> list[str]:
        """
        Fetch all video IDs from a user.

        Args:
            user_id: Platform-specific user identifier
            cookies_file: Optional path to cookies file

        Returns:
            List of video IDs

        Raises:
            Exception: If videos cannot be fetched
        """
        pass

    @abstractmethod
    def get_video_id_name(self) -> str:
        """Get the name of video ID parameter (e.g., 'bvid' for Bilibili, 'note_id' for Xiaohongshu)."""
        pass

    @abstractmethod
    def get_user_id_name(self) -> str:
        """Get the name of user ID parameter (e.g., 'mid' for Bilibili, 'user_id' for Xiaohongshu)."""
        pass
