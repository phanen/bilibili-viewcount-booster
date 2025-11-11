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
from executor import JobDispatcher, ProxyValidator, VideoBooster
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
        help='Number of consumer worker threads per video (default: 50)',
    )
    parser.add_argument(
        '--parallel-videos',
        type=int,
        default=int(get_config('PARALLEL_VIDEOS', 3)),
        help='Number of videos to process in parallel (default: 3)',
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
parallel_videos = args.parallel_videos

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

proxy_queue = Queue()
validated_queue = Queue()
proxy_cooldowns = {}
proxy_cooldown_lock = threading.Lock()


# 3. Create video boosters
console.print(f'\n[bold cyan]Preparing to boost {len(bv_ids)} video(s)[/bold cyan]')

video_boosters = []
failed_videos = []

for video_idx, bv in enumerate(bv_ids, 1):
    try:
        info = requests.get(
            f'https://api.bilibili.com/x/web-interface/view?bvid={bv}', headers={'User-Agent': UserAgent().random}
        ).json()['data']
        initial_view_count = info['stat']['view']

        booster = VideoBooster(
            bv_id=bv,
            info_dict=info,
            initial_view=initial_view_count,
            target_increment=increment_target,
            cooldown=cooldown_time,
            timeout=timeout,
        )
        video_boosters.append(booster)

        console.print(
            f'[yellow]Video {video_idx}/{len(bv_ids)}: {bv} (Initial: {initial_view_count}, Target: +{increment_target})[/yellow]'
        )
    except Exception as e:
        console.print(f'[red]Failed to prepare {bv}: {e}[/red]')
        failed_videos.append(bv)

if not video_boosters:
    console.print('[red]No videos to process. Exiting.[/red]')
    sys.exit(1)

# 4. Start the executor system
console.print('\n[bold cyan]Starting boost system[/bold cyan]')
console.print(f'[cyan]Validators: {thread_num}, Workers: {worker_threads}[/cyan]')

overall_start_time = datetime.now()

# Feed proxies to queue
for proxy in total_proxies:
    proxy_queue.put(proxy)

# Create validator
validator = ProxyValidator(proxy_queue, validated_queue, timeout=timeout)
validator.start(num_workers=thread_num)

# Create dispatcher
dispatcher = JobDispatcher(validated_queue, video_boosters, num_workers=worker_threads)
dispatcher.start()

console.print(f'[green]✓ System started with {len(total_proxies)} proxies[/green]')

# 5. Monitor progress
tracker = get_progress_tracker(progress_style)

with tracker.progress_context():
    # Add validation progress bar
    if hasattr(tracker, 'progress') and tracker.progress:
        validate_task = tracker.progress.add_task('[blue]Validation', total=len(total_proxies), status='Starting...')

    # Add video progress bars
    for booster in video_boosters:
        tracker.add_video_task(booster.bv_id, booster.target_increment, booster.initial_view)

    # Monitor loop
    while True:
        sleep(0.5)

        # Update validation progress
        stats = validator.get_stats()
        if hasattr(tracker, 'progress') and tracker.progress:
            tracker.progress.update(
                validate_task,
                completed=stats['checked'],
                status=f'Checked: {stats["checked"]}, Valid: {stats["validated"]}',
            )

        # Update video progress and check for completion
        all_complete = True
        for booster in video_boosters:
            if not booster.is_complete():
                all_complete = False
                # Periodically update view count
                booster.update_view_count()

            progress = booster.get_progress()
            tracker.update_video_progress(
                progress['bv_id'], progress['current'], progress['initial'], progress['target'], progress['hits']
            )

            if booster.is_complete() and not booster.completed:
                booster.completed = True
                tracker.mark_video_complete(
                    progress['bv_id'], progress['current'], progress['initial'], progress['target']
                )

        if all_complete:
            break

# 6. Stop workers
validator.stop()
dispatcher.stop()
sleep(1)

# 7. Summary
results = []
for booster in video_boosters:
    progress = booster.get_progress()
    results.append(
        {
            'bv': progress['bv_id'],
            'success': progress['completed'],
            'initial': progress['initial'],
            'final': progress['current'],
            'increment': progress['increment'],
            'hits': progress['hits'],
        }
    )
# 8. Final summary
overall_elapsed = int((datetime.now() - overall_start_time).total_seconds())
successful_videos = [r for r in results if r['success']]
stats = validator.get_stats()

console.print()
console.print(
    Panel.fit(
        f'[bold]Overall Summary[/bold]\n\n'
        f'[cyan]Total Time:[/cyan] {time_format(overall_elapsed)}\n'
        f'[cyan]Videos Processed:[/cyan] {len(results)}/{len(bv_ids)}\n'
        f'[cyan]Successful:[/cyan] {len(successful_videos)}\n'
        f'[cyan]Failed:[/cyan] {len(failed_videos)}\n\n'
        f'[cyan]Proxies Checked:[/cyan] {stats["checked"]}\n'
        f'[cyan]Valid Proxies:[/cyan] {stats["validated"]}\n'
        f'[cyan]Validation Rate:[/cyan] {(stats["validated"] / stats["checked"] * 100 if stats["checked"] > 0 else 0):.1f}%',
        title='[bold green]✓ Complete[/bold green]',
        border_style='green',
    )
)

if successful_videos:
    console.print('\n[bold green]Successful Videos:[/bold green]')
    for r in successful_videos:
        console.print(
            f'  • {r["bv"]}: {r["initial"]} → {r["final"]} (+{r["increment"]}) in {time_format(r["elapsed"])}'
        )

if failed_videos:
    console.print('\n[bold yellow]Failed Videos:[/bold yellow]')
    for bv in failed_videos:
        console.print(f'  • {bv}')

console.print()
