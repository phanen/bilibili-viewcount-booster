"""
Xiaohongshu (Little Red Book) platform implementation.

Note: This is a basic implementation. Xiaohongshu has anti-bot measures
and may require additional authentication/cookies for production use.
"""

import requests
from fake_useragent import UserAgent

from .base import Platform


class XiaohongshuPlatform(Platform):
    """Xiaohongshu (Little Red Book) platform implementation."""

    def get_name(self) -> str:
        """Get platform name."""
        return 'Xiaohongshu'

    def get_video_info(self, video_id: str) -> dict:
        """
        Fetch video/note information from Xiaohongshu.

        Args:
            video_id: Xiaohongshu note ID

        Returns:
            Dictionary with note info

        Note: This uses the public web API. May require authentication for production use.
        """
        headers = {
            'User-Agent': UserAgent().random,
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Referer': 'https://www.xiaohongshu.com/',
        }

        try:
            # Try web API first
            response = requests.get(
                f'https://www.xiaohongshu.com/discovery/item/{video_id}',
                headers=headers,
                timeout=10,
            )

            if response.status_code != 200:
                raise Exception(f'HTTP {response.status_code}')

            # For now, return a minimal dict with the note_id
            # In production, you'd parse the HTML/JSON response
            return {
                'note_id': video_id,
                'title': 'Xiaohongshu Note',
                'user_id': 'unknown',
            }
        except Exception as e:
            raise Exception(f'Failed to fetch note info: {e}')

    def boost_view(self, video_id: str, info_dict: dict, proxy: str, timeout: int = 5) -> bool:
        """
        Send a view boost request to Xiaohongshu through proxy.

        Args:
            video_id: Xiaohongshu note ID
            info_dict: Note information dict from get_video_info()
            proxy: Proxy address (format: ip:port)
            timeout: Request timeout in seconds

        Returns:
            True if request succeeded, False otherwise

        Note: This simulates a view by accessing the note page.
        The actual API endpoint may vary and require authentication.
        """
        headers = {
            'User-Agent': UserAgent().random,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Referer': 'https://www.xiaohongshu.com/explore',
        }

        try:
            # Simulate a view by accessing the note page
            response = requests.get(
                f'https://www.xiaohongshu.com/discovery/item/{video_id}',
                proxies={'http': 'http://' + proxy, 'https': 'http://' + proxy},
                headers=headers,
                timeout=timeout,
                verify=False,
            )
            # Consider it successful if we get a 200 or 302 (redirect)
            return response.status_code in [200, 302]
        except:
            return False

    def get_current_views(self, video_id: str) -> int:
        """
        Get current view count for a Xiaohongshu note.

        Args:
            video_id: Xiaohongshu note ID

        Returns:
            Current view count (estimated)

        Note: Xiaohongshu doesn't directly expose view counts via public API.
        This returns 0 as a placeholder. In production, you'd need to parse
        the page or use authenticated API endpoints.
        """
        # Xiaohongshu doesn't expose view counts publicly like Bilibili
        # This is a limitation of the platform
        # Return 0 to indicate we can't track it
        return 0

    def get_user_videos(self, user_id: str, cookies_file: str = None) -> list[str]:
        """
        Fetch all note IDs from a Xiaohongshu user.

        Args:
            user_id: Xiaohongshu user ID
            cookies_file: Optional path to cookies file

        Returns:
            List of note IDs

        Note: This is a stub implementation. In production, you'd need to:
        1. Use authenticated API or web scraping
        2. Parse user profile page
        3. Handle pagination
        """
        raise NotImplementedError(
            'Fetching user videos from Xiaohongshu is not yet implemented. '
            'Please provide note IDs directly using --note-ids option.'
        )

    def get_video_id_name(self) -> str:
        """Get the name of video ID parameter."""
        return 'note_id'

    def get_user_id_name(self) -> str:
        """Get the name of user ID parameter."""
        return 'user_id'
