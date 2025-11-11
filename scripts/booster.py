import argparse
import os
import random
import sys
import threading
from datetime import date, datetime, timedelta
from queue import Queue
from time import sleep

import requests

# Disable SSL warnings for expired certificates
import urllib3
from fake_useragent import UserAgent
from progress_tracker import get_progress_tracker
from rich.console import Console
from rich.panel import Panel
from utils import load_env_file, time_format

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

"""
Non-blocking pipeline architecture:
1. Proxy fetching: Get proxies from API
2. Proxy validation (75 threads): Validate proxies and put valid ones into queue
3. Proxy consumption (50 threads): Consume validated proxies immediately to boost views

Benefits:
- No waiting for all proxies to be validated before starting
- Proxies are consumed as soon as they're validated
- Parallel validation and consumption for maximum throughput
- Real-time monitoring with early exit when target is reached
"""

console = Console()


# parameters
timeout = 3  # seconds for proxy connection timeout
thread_num = 75  # thread count for filtering active proxies
# statistics tracking parameters
successful_hits = 0  # count of successful proxy requests
initial_view_count = 0  # starting view count
lock = threading.Lock()  # lock for thread-safe counter updates

# Progress tracking
tracker = None


def parse_args():
    """Parse command line arguments with priority: CLI > ENV > .env file"""
    # Load .env file first
    env_file = load_env_file()

    # Helper to get value from env or .env
    def get_config(key, default=None):
        return os.getenv(key) or env_file.get(key) or default

    parser = argparse.ArgumentParser(
        description='Bilibili View Count Booster - A non-blocking pipeline to boost video views using proxies',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single video
  python booster.py --bvids BV1xxx --increment 1000
  python booster.py --bv BV1xxx -n 1000

  # Multiple videos
  python booster.py --bvids BV1xxx BV2yyy BV3zzz -n 100

  # All videos from a user
  python booster.py --mid 123456 -n 50 --cookies cookies.txt

  # Using custom proxy URL
  python booster.py --bv BV1xxx -n 1000 --proxy-url https://example.com/proxies.txt

  # Force progress style
  python booster.py --bv BV1xxx -n 100 --progress-style ci
        """,
    )

    # Video selection (mutually exclusive)
    video_group = parser.add_mutually_exclusive_group(required=False)
    video_group.add_argument(
        '--bvids', '--bv', nargs='+', default=None, help='One or more BV IDs to boost (e.g., BV1abc BV2def)'
    )
    video_group.add_argument('--mid', type=int, help='User MID to boost all their videos')

    parser.add_argument(
        '--increment',
        '-n',
        type=int,
        default=int(get_config('DEFAULT_INCREMENT', 0)),
        help='View count increment target (default: from env or 0)',
    )
    parser.add_argument(
        '--cookies',
        default=get_config('BILIBILI_COOKIES_FILE'),
        help='Path to cookies file for fetching user videos (required with --mid)',
    )

    proxy_group = parser.add_mutually_exclusive_group()
    proxy_group.add_argument(
        '--proxy-url',
        default=get_config(
            'PROXY_URL',
            'https://raw.githubusercontent.com/Skillter/ProxyGather/refs/heads/master/proxies/working-proxies-all.txt',
        ),
        help='URL to fetch proxies from (default: ProxyGather working proxies)',
    )
    proxy_group.add_argument('--proxy-file', help='Local file containing proxies (one per line)')
    proxy_group.add_argument(
        '--use-archive', action='store_true', help='Use checkerproxy.net archive (original source)'
    )

    parser.add_argument(
        '--validators',
        type=int,
        default=int(get_config('VALIDATORS', 75)),
        help='Number of validator threads (default: 75)',
    )
    parser.add_argument(
        '--workers',
        type=int,
        default=int(get_config('WORKERS', 50)),
        help='Number of consumer worker threads (default: 50)',
    )
    parser.add_argument(
        '--cooldown',
        type=int,
        default=int(get_config('COOLDOWN', 300)),
        help='Cooldown time per proxy in seconds (default: 300)',
    )
    parser.add_argument(
        '--timeout', type=int, default=int(get_config('TIMEOUT', 3)), help='Request timeout in seconds (default: 3)'
    )
    parser.add_argument(
        '--blacklist',
        type=str,
        default=get_config('BLACKLIST', ''),
        help='Comma-separated list of BV IDs to exclude (blacklist)',
    )
    parser.add_argument(
        '--progress-style',
        choices=['auto', 'rich', 'ci'],
        default=get_config('PROGRESS_STYLE', 'auto'),
        help='Progress display style: auto (detect from CI env), rich (fancy bars), ci (simple logging). Default: auto',
    )

    args = parser.parse_args()

    # Handle --mid from .env if not provided via CLI
    if not args.mid and get_config('BILIBILI_USER_MID'):
        args.mid = int(get_config('BILIBILI_USER_MID'))

    # Handle BV_ID from env if not provided via CLI
    if not args.bvids and not args.mid and get_config('BV_ID'):
        args.bvids = [get_config('BV_ID')]

    # Validate required arguments
    if not args.bvids and not args.mid:
        parser.error(
            'Video selection required: provide --bvids (or --bv), or --mid (or set BV_ID/BILIBILI_USER_MID in env)'
        )
    if not args.increment:
        parser.error('Target increment view count is required (use --increment or -n, or set DEFAULT_INCREMENT in env)')
    if args.mid and not args.cookies:
        parser.error('--cookies is required when using --mid')

    return args


def fetch_proxies_from_url(url: str) -> list[str]:
    """Fetch proxies from a URL"""
    console.print(f'[cyan]Fetching proxies from {url}...[/cyan]')
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            # Try to parse as plain text list (one proxy per line)
            proxies = [line.strip() for line in response.text.split('\n') if line.strip() and not line.startswith('#')]
            if proxies:
                console.print(f'[green]✓ Successfully fetched {len(proxies)} proxies[/green]')
                return proxies
        console.print(f'[red]Failed to fetch proxies: HTTP {response.status_code}[/red]')
    except Exception as e:
        console.print(f'[red]Error fetching proxies: {e}[/red]')
    return []


def fetch_proxies_from_file(filepath: str) -> list[str]:
    """Load proxies from a local file"""
    console.print(f'[cyan]Loading proxies from {filepath}...[/cyan]')
    try:
        with open(filepath, 'r') as f:
            proxies = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        console.print(f'[green]✓ Successfully loaded {len(proxies)} proxies[/green]')
        return proxies
    except Exception as e:
        console.print(f'[red]Error loading proxies: {e}[/red]')
        return []


def fetch_proxies_from_archive() -> list[str]:
    """Fetch proxies from checkerproxy.net archive (original method)"""
    console.print('[cyan]Using checkerproxy.net archive...[/cyan]')
    day = date.today()
    for _ in range(30):  # Try last 30 days
        day = day - timedelta(days=1)
        proxy_url = f'https://api.checkerproxy.net/v1/landing/archive/{day.strftime_format("%Y-%m-%d")}'
        console.print(f'[cyan]Trying {day.strftime_format("%Y-%m-%d")}...[/cyan]')
        try:
            response = requests.get(proxy_url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                proxies_obj = data['data']['proxyList']
                if isinstance(proxies_obj, list):
                    proxies = proxies_obj
                elif isinstance(proxies_obj, dict):
                    proxies = [proxy for proxy in proxies_obj.values() if proxy]
                else:
                    continue

                if len(proxies) > 100:
                    console.print(f'[green]✓ Successfully got {len(proxies)} proxies[/green]')
                    return proxies
                else:
                    console.print(f'[yellow]Only {len(proxies)} proxies available[/yellow]')
        except Exception as e:
            console.print(f'[red]Error: {e}[/red]')
            continue

    console.print('[red]Failed to fetch proxies from archive[/red]')
    return []


# Parse arguments
args = parse_args()

# Get list of BV IDs to process
bv_ids = []
if args.bvids:
    bv_ids = args.bvids
elif args.mid:
    from fetch_author_videos import get_user_videos

    console.print(f'[cyan]Fetching videos from user {args.mid}...[/cyan]')
    bv_ids = get_user_videos(args.mid, cookies_file=args.cookies)
    if not bv_ids:
        console.print('[red]No videos found for user[/red]')
        sys.exit(1)
    console.print(f'[green]Found {len(bv_ids)} videos[/green]')

# Apply blacklist filter
blacklist = [b.strip() for b in args.blacklist.split(',') if b.strip()]
if blacklist:
    original_count = len(bv_ids)
    bv_ids = [bv for bv in bv_ids if bv not in blacklist]
    filtered_count = original_count - len(bv_ids)
    if filtered_count > 0:
        console.print(f'[yellow]Filtered out {filtered_count} blacklisted video(s)[/yellow]')
    if not bv_ids:
        console.print('[red]All videos are blacklisted, nothing to process[/red]')
        sys.exit(0)

increment_target = args.increment
timeout = args.timeout
thread_num = args.validators
worker_threads = args.workers
cooldown_time = args.cooldown
progress_style = args.progress_style

# 1. Get proxies
console.print()
if args.proxy_file:
    total_proxies = fetch_proxies_from_file(args.proxy_file)
elif args.use_archive:
    total_proxies = fetch_proxies_from_archive()
else:
    total_proxies = fetch_proxies_from_url(args.proxy_url)

if not total_proxies:
    console.print('[red]No proxies available. Exiting.[/red]')
    sys.exit(1)

# 2. Setup pipeline queues
if len(total_proxies) > 10000:
    console.print('[yellow]More than 10000 proxies, randomly picking 10000 proxies[/yellow]')
    random.shuffle(total_proxies)
    total_proxies = total_proxies[:10000]

proxy_queue = Queue()  # raw proxies to be validated
validated_queue = Queue()  # validated proxies ready to use
stop_event = threading.Event()  # signal to stop all threads
checked_count = 0
validated_count = 0
fetched_count = 0  # count of proxies fetched
proxy_cooldown = {}  # track last use time for each proxy
proxy_cooldown_lock = threading.Lock()


def proxy_validator():
    """Validates proxies and puts them in validated_queue"""
    global checked_count, validated_count
    while not stop_event.is_set():
        try:
            proxy = proxy_queue.get(timeout=1)
        except:
            continue

        with lock:
            checked_count += 1

        try:
            requests.post('http://httpbin.org/post', proxies={'http': 'http://' + proxy}, timeout=timeout)
            validated_queue.put(proxy)
            with lock:
                validated_count += 1
        except:
            pass

        proxy_queue.task_done()


def proxy_consumer(info_dict):
    """Consumes validated proxies and boosts view count"""
    global successful_hits, initial_view_count

    while not stop_event.is_set():
        try:
            proxy = validated_queue.get(timeout=1)
        except:
            continue

        # Check if proxy is in cooldown
        with proxy_cooldown_lock:
            last_used = proxy_cooldown.get(proxy, 0)
            now = datetime.now().timestamp()
            if now - last_used < cooldown_time:
                # Put it back for later
                validated_queue.put(proxy)
                validated_queue.task_done()
                sleep(1)
                continue

        try:
            requests.post(
                'http://api.bilibili.com/x/click-interface/click/web/h5',
                proxies={'http': 'http://' + proxy},
                headers={'User-Agent': UserAgent().random},
                timeout=timeout,
                data={
                    'aid': info_dict['aid'],
                    'cid': info_dict['cid'],
                    'bvid': bv,
                    'part': '1',
                    'mid': info_dict['owner']['mid'],
                    'jsonp': 'jsonp',
                    'type': info_dict['desc_v2'][0]['type'] if info_dict['desc_v2'] else '1',
                    'sub_type': '0',
                },
            )
            with lock:
                successful_hits += 1
            with proxy_cooldown_lock:
                proxy_cooldown[proxy] = datetime.now().timestamp()
            # Put proxy back in queue for reuse after cooldown
            validated_queue.put(proxy)
        except:
            pass

        validated_queue.task_done()


# 3. Process each video
console.print(f'\n[bold cyan]Starting to boost {len(bv_ids)} video(s)[/bold cyan]')

overall_start_time = datetime.now()
successful_videos = []
failed_videos = []

for video_idx, bv in enumerate(bv_ids, 1):
    console.print(f'\n[bold yellow]Video {video_idx}/{len(bv_ids)}: {bv}[/bold yellow]')

    try:
        info = requests.get(
            f'https://api.bilibili.com/x/web-interface/view?bvid={bv}', headers={'User-Agent': UserAgent().random}
        ).json()['data']
        initial_view_count = info['stat']['view']
        target_view_count = initial_view_count + increment_target
        console.print(f'[green]Initial view count: {initial_view_count}[/green]')
        console.print(f'[cyan]Target: +{increment_target} views (reach {target_view_count})[/cyan]')
    except Exception as e:
        console.print(f'[red]Failed to get initial view count: {e}[/red]')
        failed_videos.append(bv)
        continue

    # Reset counters for this video
    checked_count = 0
    validated_count = 0
    fetched_count = 0
    successful_hits = 0

    # 4. Start the pipeline with progress tracker
    tracker = get_progress_tracker(progress_style)
    start_pipeline_time = datetime.now()

    with tracker.progress_context():
        # Create progress tasks
        tracker.create_tasks(len(total_proxies), increment_target, bv, bv_ids, video_idx)

        # Start validator threads
        validator_threads = []
        for _ in range(thread_num):
            thread = threading.Thread(target=proxy_validator, daemon=True)
            thread.start()
            validator_threads.append(thread)

        # Start consumer threads
        consumer_threads = []
        for _ in range(worker_threads):
            thread = threading.Thread(target=proxy_consumer, args=(info,), daemon=True)
            thread.start()
            consumer_threads.append(thread)

        # Monitor progress and check target
        current = initial_view_count
        check_interval = 5  # check view count every 5 seconds
        last_check_time = datetime.now()
        target_reached = False
        proxy_index = 0

        while not target_reached:
            # Feed proxies continuously
            if proxy_index < len(total_proxies):
                batch_size = min(100, len(total_proxies) - proxy_index)
                for i in range(batch_size):
                    proxy_queue.put(total_proxies[proxy_index])
                    proxy_index += 1
                    fetched_count = proxy_index
                    tracker.update_fetch(fetched_count, len(total_proxies), f'Fetched: {fetched_count}')

                if proxy_index >= len(total_proxies):
                    tracker.update_fetch(fetched_count, len(total_proxies), '✓ All fetched, recycling...')
            else:
                # Keep feeding validated proxies back for reuse
                tracker.update_fetch(
                    fetched_count, len(total_proxies), f'✓ Recycling proxies (Total: {len(total_proxies)})'
                )

            sleep(0.5)

            # Update status messages
            tracker.update_validate(checked_count, validated_count)
            tracker.update_consume(current, initial_view_count, increment_target, successful_hits)

            # Periodically check view count
            if (datetime.now() - last_check_time).total_seconds() >= check_interval:
                try:
                    response = requests.get(
                        f'https://api.bilibili.com/x/web-interface/view?bvid={bv}',
                        headers={'User-Agent': UserAgent().random},
                    ).json()
                    current = response['data']['stat']['view']
                    current_increment = current - initial_view_count

                    if current_increment >= increment_target:
                        tracker.mark_complete(current, initial_view_count, increment_target, bv, video_idx)
                        target_reached = True
                        stop_event.set()
                        break
                    else:
                        tracker.update_status(current, initial_view_count, increment_target, successful_hits)
                except:
                    pass
                last_check_time = datetime.now()

        # Signal all threads to stop
        stop_event.set()

        # Give threads time to finish current work
        sleep(2)

        # Final updates
        tracker.finalize(fetched_count, checked_count, validated_count, current, increment_target)

    pipeline_cost_seconds = int((datetime.now() - start_pipeline_time).total_seconds())

    # Get final view count
    try:
        response = requests.get(
            f'https://api.bilibili.com/x/web-interface/view?bvid={bv}', headers={'User-Agent': UserAgent().random}
        ).json()
        current = response['data']['stat']['view']
    except:
        pass

    # Summary for this video
    view_increase = current - initial_view_count
    target_reached = view_increase >= increment_target

    if target_reached:
        successful_videos.append(bv)
    else:
        failed_videos.append(bv)

    view_increase_color = 'green' if target_reached else 'yellow'
    target_status = '✓ Reached!' if target_reached else '(not reached)'
    title = (
        f'[bold green]✓ {bv} Complete[/bold green]'
        if target_reached
        else f'[bold yellow]⚠ {bv} Incomplete[/bold yellow]'
    )
    border_style = 'green' if target_reached else 'yellow'

    console.print()
    console.print(
        Panel.fit(
            f'[bold]Video Summary[/bold]\n\n'
            f'[cyan]Time Elapsed:[/cyan] {time_format(pipeline_cost_seconds)}\n'
            f'[cyan]Proxies Checked:[/cyan] {checked_count}/{len(total_proxies)}\n'
            f'[cyan]Valid Proxies:[/cyan] {validated_count}\n'
            f'[cyan]Successful Hits:[/cyan] {successful_hits}\n'
            f'[cyan]Success Rate:[/cyan] {(successful_hits / validated_count * 100 if validated_count > 0 else 0):.2f}%\n\n'
            f'[cyan]Initial Views:[/cyan] {initial_view_count}\n'
            f'[cyan]Final Views:[/cyan] {current}\n'
            f'[{view_increase_color}]View Increase:[/{view_increase_color}] +{view_increase}\n'
            f'[{view_increase_color}]Target Increment:[/{view_increase_color}] +{increment_target} {target_status}',
            title=title,
            border_style=border_style,
        )
    )

# Overall summary for multiple videos
if len(bv_ids) > 1:
    overall_time = int((datetime.now() - overall_start_time).total_seconds())
    console.print()
    console.print(
        Panel.fit(
            f'[bold]Overall Summary[/bold]\n\n'
            f'[cyan]Total Time:[/cyan] {time_format(overall_time)}\n'
            f'[cyan]Total Videos:[/cyan] {len(bv_ids)}\n'
            f'[green]Successful:[/green] {len(successful_videos)}\n'
            f'[red]Failed:[/red] {len(failed_videos)}\n\n'
            + ('\n'.join(f'[green]✓[/green] {vid}' for vid in successful_videos) if successful_videos else '')
            + ('\n' if successful_videos and failed_videos else '')
            + ('\n'.join(f'[red]✗[/red] {vid}' for vid in failed_videos) if failed_videos else ''),
            title='[bold cyan]Batch Complete[/bold cyan]',
            border_style='green' if not failed_videos else 'yellow',
        )
    )

console.print()
