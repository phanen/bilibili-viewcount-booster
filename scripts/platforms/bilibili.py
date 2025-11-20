"""
Bilibili platform implementation.
"""

import requests
from fake_useragent import UserAgent

from .base import Platform


class BilibiliPlatform(Platform):
    """Bilibili platform implementation."""

    def get_name(self) -> str:
        """Get platform name."""
        return 'Bilibili'

    def get_video_info(self, video_id: str) -> dict:
        """
        Fetch video information from Bilibili.

        Args:
            video_id: Bilibili BV ID

        Returns:
            Dictionary with video info from Bilibili API
        """
        response = requests.get(
            f'https://api.bilibili.com/x/web-interface/view?bvid={video_id}',
            headers={'User-Agent': UserAgent().random},
        )
        data = response.json()
        if data['code'] != 0:
            raise Exception(f'Failed to fetch video info: {data.get("message", "Unknown error")}')
        return data['data']

    def boost_view(self, video_id: str, info_dict: dict, proxy: str, timeout: int = 5) -> bool:
        """
        Send a view boost request to Bilibili through proxy.

        Args:
            video_id: Bilibili BV ID
            info_dict: Video information dict from get_video_info()
            proxy: Proxy address (format: ip:port)
            timeout: Request timeout in seconds

        Returns:
            True if request succeeded, False otherwise
        """
        try:
            requests.post(
                'http://api.bilibili.com/x/click-interface/click/web/h5',
                proxies={'http': 'http://' + proxy},
                headers={'User-Agent': UserAgent().random},
                timeout=timeout,
                verify=False,
                data={
                    'aid': info_dict['aid'],
                    'cid': info_dict['cid'],
                    'bvid': video_id,
                    'part': '1',
                    'mid': info_dict['owner']['mid'],
                    'jsonp': 'jsonp',
                    'type': info_dict['desc_v2'][0]['type'] if info_dict['desc_v2'] else '1',
                    'sub_type': '0',
                },
            )
            return True
        except:
            return False

    def get_current_views(self, video_id: str) -> int:
        """
        Get current view count for a Bilibili video.

        Args:
            video_id: Bilibili BV ID

        Returns:
            Current view count
        """
        try:
            response = requests.get(
                f'https://api.bilibili.com/x/web-interface/view?bvid={video_id}',
                headers={'User-Agent': UserAgent().random},
                timeout=5,
            )
            data = response.json()
            return data['data']['stat']['view']
        except:
            raise Exception(f'Failed to fetch current views for {video_id}')

    def get_user_videos(self, user_id: str, cookies_file: str = None) -> list[str]:
        """
        Fetch all video BVIDs from a Bilibili user.

        Args:
            user_id: Bilibili user MID
            cookies_file: Optional path to cookies file

        Returns:
            List of BV IDs
        """
        from fetch_author_videos import get_user_videos

        return get_user_videos(int(user_id), cookies_file=cookies_file)

    def get_video_id_name(self) -> str:
        """Get the name of video ID parameter."""
        return 'bvid'

    def get_user_id_name(self) -> str:
        """Get the name of user ID parameter."""
        return 'mid'
