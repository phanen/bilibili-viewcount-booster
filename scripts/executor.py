"""
Job executor for managing proxy validation and video boosting tasks.
"""

import threading
from datetime import datetime
from queue import Empty
from time import sleep

import requests
from fake_useragent import UserAgent


class ProxyValidator:
    """Validates proxies continuously."""

    def __init__(self, proxy_queue, validated_queue, timeout=5):
        self.proxy_queue = proxy_queue
        self.validated_queue = validated_queue
        self.timeout = timeout
        self.stop_event = threading.Event()
        self.checked_count = 0
        self.validated_count = 0
        self.lock = threading.Lock()

    def validate_worker(self):
        """Worker thread for validating proxies."""
        while not self.stop_event.is_set():
            try:
                proxy = self.proxy_queue.get(timeout=1)
            except Empty:
                continue

            with self.lock:
                self.checked_count += 1

            try:
                requests.post(
                    'http://httpbin.org/post', proxies={'http': 'http://' + proxy}, timeout=self.timeout, verify=False
                )
                self.validated_queue.put(proxy)
                with self.lock:
                    self.validated_count += 1
            except:
                pass

            self.proxy_queue.task_done()

    def start(self, num_workers=75):
        """Start validation workers."""
        self.workers = []
        for _ in range(num_workers):
            worker = threading.Thread(target=self.validate_worker, daemon=True)
            worker.start()
            self.workers.append(worker)

    def stop(self):
        """Stop all workers."""
        self.stop_event.set()

    def get_stats(self):
        """Get validation statistics."""
        with self.lock:
            return {'checked': self.checked_count, 'validated': self.validated_count}


class VideoBooster:
    """Manages boosting for a single video."""

    def __init__(self, bv_id, info_dict, initial_view, target_increment, cooldown=300, timeout=5):
        self.bv_id = bv_id
        self.info_dict = info_dict
        self.initial_view = initial_view
        self.target_increment = target_increment
        self.cooldown = cooldown
        self.timeout = timeout

        self.current_view = initial_view
        self.hits = 0
        self.proxy_cooldowns = {}  # {proxy: last_used_timestamp}
        self.lock = threading.Lock()
        self.completed = False
        self.start_time = datetime.now()
        self.end_time = None

    def can_use_proxy(self, proxy):
        """Check if proxy can be used (not in cooldown)."""
        with self.lock:
            last_used = self.proxy_cooldowns.get(proxy, 0)
            now = datetime.now().timestamp()
            return (now - last_used) >= self.cooldown

    def use_proxy(self, proxy):
        """Attempt to boost views using this proxy."""
        if not self.can_use_proxy(proxy):
            return False

        try:
            requests.post(
                'http://api.bilibili.com/x/click-interface/click/web/h5',
                proxies={'http': 'http://' + proxy},
                headers={'User-Agent': UserAgent().random},
                timeout=self.timeout,
                verify=False,
                data={
                    'aid': self.info_dict['aid'],
                    'cid': self.info_dict['cid'],
                    'bvid': self.bv_id,
                    'part': '1',
                    'mid': self.info_dict['owner']['mid'],
                    'jsonp': 'jsonp',
                    'type': self.info_dict['desc_v2'][0]['type'] if self.info_dict['desc_v2'] else '1',
                    'sub_type': '0',
                },
            )
            with self.lock:
                self.hits += 1
                self.proxy_cooldowns[proxy] = datetime.now().timestamp()
            return True
        except:
            return False

    def update_view_count(self):
        """Fetch current view count from Bilibili."""
        try:
            response = requests.get(
                f'https://api.bilibili.com/x/web-interface/view?bvid={self.bv_id}',
                headers={'User-Agent': UserAgent().random},
                timeout=self.timeout,
            ).json()
            with self.lock:
                self.current_view = response['data']['stat']['view']
            return self.current_view
        except:
            return self.current_view

    def is_complete(self):
        """Check if target is reached."""
        with self.lock:
            is_done = (self.current_view - self.initial_view) >= self.target_increment
            if is_done and not self.completed:
                self.end_time = datetime.now()
                self.completed = True
            return is_done

    def get_progress(self):
        """Get current progress."""
        with self.lock:
            elapsed = 0
            if self.end_time:
                elapsed = int((self.end_time - self.start_time).total_seconds())
            elif self.completed:
                elapsed = int((datetime.now() - self.start_time).total_seconds())

            return {
                'bv_id': self.bv_id,
                'current': self.current_view,
                'initial': self.initial_view,
                'increment': self.current_view - self.initial_view,
                'target': self.target_increment,
                'hits': self.hits,
                'completed': self.completed,
                'elapsed': elapsed,
            }


class JobDispatcher:
    """Dispatches validated proxies to video boosters."""

    def __init__(self, validated_queue, video_boosters, num_workers=50):
        self.validated_queue = validated_queue
        self.video_boosters = video_boosters
        self.num_workers = num_workers
        self.stop_event = threading.Event()
        self.workers = []
        self.round_robin_index = 0
        self.lock = threading.Lock()

    def dispatch_worker(self):
        """Worker thread that dispatches proxies to videos."""
        while not self.stop_event.is_set():
            try:
                proxy = self.validated_queue.get(timeout=1)
            except Empty:
                continue

            # Find an available video (round-robin with filtering)
            video = self._get_next_video()

            if video is None:
                # All videos complete or none available
                self.validated_queue.put(proxy)
                self.validated_queue.task_done()
                sleep(0.1)
                continue

            # Try to use proxy for this video
            if video.use_proxy(proxy):
                # Success - put proxy back for reuse
                self.validated_queue.put(proxy)
            else:
                # Proxy in cooldown - put it back
                self.validated_queue.put(proxy)

            self.validated_queue.task_done()

    def _get_next_video(self):
        """Get next available video that's not complete."""
        with self.lock:
            incomplete_videos = [v for v in self.video_boosters if not v.is_complete()]
            if not incomplete_videos:
                return None

            # Round-robin through incomplete videos
            self.round_robin_index = self.round_robin_index % len(incomplete_videos)
            video = incomplete_videos[self.round_robin_index]
            self.round_robin_index += 1
            return video

    def start(self):
        """Start dispatcher workers."""
        for _ in range(self.num_workers):
            worker = threading.Thread(target=self.dispatch_worker, daemon=True)
            worker.start()
            self.workers.append(worker)

    def stop(self):
        """Stop all workers."""
        self.stop_event.set()
