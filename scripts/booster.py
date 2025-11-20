"""
Multi-Platform View Count Booster - Main Script

Simulates video views by sending HTTP requests to platform APIs
through validated proxy servers. Supports multiple platforms:
- Bilibili (default)
- Xiaohongshu (Little Red Book)

1. Fetch Proxies - Download free proxy lists from public sources
2. Validate Proxies (75 threads) - Test proxies against httpbin.org
3. Boost Views (50 threads) - Send view requests through valid proxies
4. Cooldown Management - 5-minute wait per proxy to avoid rate limiting
"""

import argparse
import os
import random
import sys
from datetime import date, datetime, timedelta
from queue import Queue

import requests
import urllib3

# Local imports
from executor import JobDispatcher, ProxyValidator, VideoBooster
from platforms import PLATFORMS, get_platform
from progress_tracker import get_progress_tracker
from rich.console import Console
from rich.panel import Panel
from signal_handler import ShutdownHandler
from utils import load_env_file, time_format

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

console = Console()


def parse_args():
    """Parse command line arguments with priority: CLI > ENV > .env file"""
    env_file = load_env_file()

    def get_config(key, default=None):
        return os.getenv(key) or env_file.get(key) or default

    parser = argparse.ArgumentParser(
        description='Multi-Platform View Count Booster - Non-blocking pipeline for boosting video views',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Bilibili - Single video
  python booster.py --platform bilibili --video-ids BV1xxx --increment 1000
  
  # Bilibili - Multiple videos
  python booster.py --platform bilibili --video-ids BV1xxx BV2yyy -n 100
  
  # Bilibili - All videos from a user
  python booster.py --platform bilibili --user-id 123456 -n 50 --cookies cookies.txt
  
  # Xiaohongshu - Single note
  python booster.py --platform xiaohongshu --video-ids 63f9a8b0000000001f03e6a1 -n 100
  
  # Custom proxy source
  python booster.py --video-ids BV1xxx -n 1000 --proxy-url https://example.com/proxies.txt
  
  # Backward compatibility (defaults to Bilibili)
  python booster.py --bvids BV1xxx -n 100
        """,
    )

    # Platform selection
    parser.add_argument(
        '--platform',
        '-p',
        choices=list(PLATFORMS.keys()),
        default=get_config('PLATFORM', 'bilibili'),
        help='Platform to boost views on (default: bilibili)',
    )

    # Video selection
    video_group = parser.add_mutually_exclusive_group(required=False)
    video_group.add_argument(
        '--video-ids',
        '--vid',
        nargs='+',
        default=None,
        help='One or more video/note IDs to boost (platform-specific format)',
    )
    video_group.add_argument(
        '--user-id', '--uid', type=str, help='User ID to boost all their videos (platform-specific format)'
    )
    # Backward compatibility with Bilibili-specific args
    video_group.add_argument('--bvids', '--bv', nargs='+', default=None, help='[DEPRECATED] Use --video-ids instead')
    video_group.add_argument('--mid', type=int, help='[DEPRECATED] Use --user-id instead')

    parser.add_argument(
        '--increment',
        '-n',
        type=int,
        default=int(get_config('DEFAULT_INCREMENT', 0)),
        help='View count increment target',
    )
    parser.add_argument(
        '--cookies',
        default=get_config('BILIBILI_COOKIES_FILE'),
        help='Path to cookies file (required with --mid)',
    )

    # Proxy source
    proxy_group = parser.add_mutually_exclusive_group()
    proxy_group.add_argument(
        '--proxy-url',
        default=get_config(
            'PROXY_URL',
            'https://raw.githubusercontent.com/Skillter/ProxyGather/refs/heads/master/proxies/working-proxies-all.txt',
        ),
        help='URL to fetch proxies from',
    )
    proxy_group.add_argument('--proxy-file', help='Local file containing proxies')
    proxy_group.add_argument('--use-archive', action='store_true', help='Use checkerproxy.net archive')

    # Performance tuning
    parser.add_argument(
        '--validators', type=int, default=int(get_config('VALIDATORS', 75)), help='Validator threads (default: 75)'
    )
    parser.add_argument(
        '--workers', type=int, default=int(get_config('WORKERS', 50)), help='Worker threads per video (default: 50)'
    )
    parser.add_argument(
        '--cooldown',
        type=int,
        default=int(get_config('COOLDOWN', 300)),
        help='Proxy cooldown in seconds (default: 300)',
    )
    parser.add_argument(
        '--timeout', type=int, default=int(get_config('TIMEOUT', 3)), help='Request timeout in seconds (default: 3)'
    )

    # Filtering
    parser.add_argument(
        '--blacklist', type=str, default=get_config('BLACKLIST', ''), help='Comma-separated video IDs to exclude'
    )

    # Display
    parser.add_argument(
        '--progress-style',
        choices=['auto', 'rich', 'ci'],
        default=get_config('PROGRESS_STYLE', 'auto'),
        help='Progress display style (default: auto)',
    )

    args = parser.parse_args()

    # Handle backward compatibility with deprecated args
    if args.bvids and not args.video_ids:
        args.video_ids = args.bvids
        args.platform = 'bilibili'
    if args.mid and not args.user_id:
        args.user_id = str(args.mid)
        args.platform = 'bilibili'

    # Handle env fallbacks
    if not args.user_id and get_config('BILIBILI_USER_MID'):
        args.user_id = get_config('BILIBILI_USER_MID')
        if args.platform == 'bilibili':
            args.platform = 'bilibili'
    if not args.video_ids and not args.user_id and get_config('BV_ID'):
        args.video_ids = [get_config('BV_ID')]
        args.platform = 'bilibili'

    # Validation
    if not args.video_ids and not args.user_id:
        parser.error('Video selection required: --video-ids or --user-id (or deprecated --bvids/--mid)')
    if not args.increment:
        parser.error('Target increment required: --increment or -n')
    if args.user_id and not args.cookies:
        parser.error('--cookies required when using --user-id')

    return args


def fetch_proxies_from_url(url: str) -> list[str]:
    """Fetch proxies from a URL."""
    console.print(f'[cyan]Fetching proxies from {url}...[/cyan]')
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            proxies = [line.strip() for line in response.text.split('\n') if line.strip() and not line.startswith('#')]
            if proxies:
                console.print(f'[green]✓ Successfully fetched {len(proxies)} proxies[/green]')
                return proxies
        console.print(f'[red]Failed to fetch proxies: HTTP {response.status_code}[/red]')
    except Exception as e:
        console.print(f'[red]Error fetching proxies: {e}[/red]')
    return []


def fetch_proxies_from_file(filepath: str) -> list[str]:
    """Load proxies from a local file."""
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
    """Fetch proxies from checkerproxy.net archive."""
    console.print('[cyan]Using checkerproxy.net archive...[/cyan]')
    day = date.today()
    for _ in range(30):
        day = day - timedelta(days=1)
        proxy_url = f'https://api.checkerproxy.net/v1/landing/archive/{day.strftime("%Y-%m-%d")}'
        console.print(f'[cyan]Trying {day.strftime("%Y-%m-%d")}...[/cyan]')
        try:
            response = requests.get(proxy_url, timeout=10, verify=False)
            if response.status_code == 200:
                data = response.json()
                proxies_obj = data['data']['proxyList']
                proxies = proxies_obj if isinstance(proxies_obj, list) else [p for p in proxies_obj.values() if p]

                if len(proxies) > 100:
                    console.print(f'[green]✓ Successfully got {len(proxies)} proxies[/green]')
                    return proxies
                console.print(f'[yellow]Only {len(proxies)} proxies available[/yellow]')
        except Exception as e:
            console.print(f'[red]Error: {e}[/red]')
            continue

    console.print('[red]Failed to fetch proxies from archive[/red]')
    return []


def get_video_list(args, platform):
    """Get list of video IDs to process based on arguments."""
    if args.video_ids:
        return args.video_ids

    if args.user_id:
        console.print(f'[cyan]Fetching videos from user {args.user_id} on {platform.get_name()}...[/cyan]')
        video_ids = platform.get_user_videos(args.user_id, cookies_file=args.cookies)
        if not video_ids:
            console.print('[red]No videos found for user[/red]')
            sys.exit(1)
        console.print(f'[green]Found {len(video_ids)} videos[/green]')
        return video_ids

    return []


def apply_blacklist(video_ids, blacklist_str):
    """Apply blacklist filter to video IDs."""
    if not blacklist_str:
        return video_ids

    blacklist = [b.strip() for b in blacklist_str.split(',') if b.strip()]
    if not blacklist:
        return video_ids

    original_count = len(video_ids)
    filtered_ids = [vid for vid in video_ids if vid not in blacklist]
    filtered_count = original_count - len(filtered_ids)

    if filtered_count > 0:
        console.print(f'[yellow]Filtered out {filtered_count} blacklisted video(s)[/yellow]')
    if not filtered_ids:
        console.print('[red]All videos are blacklisted[/red]')
        sys.exit(0)

    return filtered_ids


def prepare_video_boosters(video_ids, increment_target, platform, cooldown_time, timeout):
    """Prepare VideoBooster instances for each video."""
    console.print(f'\n[bold cyan]Preparing to boost {len(video_ids)} video(s) on {platform.get_name()}[/bold cyan]')

    video_boosters = []
    failed_videos = []

    for video_idx, video_id in enumerate(video_ids, 1):
        try:
            info = platform.get_video_info(video_id)
            initial_view_count = info.get('stat', {}).get('view', 0) if 'stat' in info else 0

            booster = VideoBooster(
                video_id=video_id,
                info_dict=info,
                initial_view=initial_view_count,
                target_increment=increment_target,
                platform=platform,
                cooldown=cooldown_time,
                timeout=timeout,
            )
            video_boosters.append(booster)

            console.print(
                f'[yellow]Video {video_idx}/{len(video_ids)}: {video_id} '
                f'(Initial: {initial_view_count}, Target: +{increment_target})[/yellow]'
            )
        except Exception as e:
            console.print(f'[red]Failed to prepare {video_id}: {e}[/red]')
            failed_videos.append(video_id)

    return video_boosters, failed_videos


def run_pipeline(args, video_boosters, total_proxies):
    """Run the main pipeline with progress tracking."""
    overall_start_time = datetime.now()

    # Initialize queues
    proxy_queue = Queue()
    validated_queue = Queue()

    # Feed proxies to queue
    for proxy in total_proxies:
        proxy_queue.put(proxy)

    # Create workers
    validator = ProxyValidator(proxy_queue, validated_queue, timeout=args.timeout)
    validator.start(num_workers=args.validators)

    dispatcher = JobDispatcher(validated_queue, video_boosters, num_workers=args.workers)
    dispatcher.start()

    console.print(f'[green]✓ System started with {len(total_proxies)} proxies[/green]')

    # Monitor progress
    tracker = get_progress_tracker(args.progress_style)

    with tracker.progress_context():
        # Add validation progress bar
        if hasattr(tracker, 'progress') and tracker.progress:
            validate_task = tracker.progress.add_task(
                '[blue]Validation', total=len(total_proxies), status='Starting...'
            )

        # Add video progress bars
        for booster in video_boosters:
            tracker.add_video_task(booster.bv_id, booster.target_increment, booster.initial_view)

        # Monitor loop
        shutdown_handler = ShutdownHandler()
        shutdown_handler.install()

        try:
            while True:
                # Check for shutdown
                if shutdown_handler.is_shutdown_requested():
                    console.print('[yellow]Gracefully shutting down...[/yellow]')
                    break

                # Update validation progress
                stats = validator.get_stats()
                if hasattr(tracker, 'progress') and tracker.progress:
                    tracker.progress.update(
                        validate_task,
                        completed=stats['checked'],
                        status=f'Checked: {stats["checked"]}, Valid: {stats["validated"]}',
                    )

                # Update video progress
                all_complete = True
                for booster in video_boosters:
                    if not booster.is_complete():
                        all_complete = False
                        booster.update_view_count()

                    progress = booster.get_progress()
                    tracker.update_video_progress(
                        progress['bv_id'],
                        progress['current'],
                        progress['initial'],
                        progress['target'],
                        progress['hits'],
                    )

                    if booster.is_complete() and not booster.completed:
                        booster.completed = True
                        tracker.mark_video_complete(
                            progress['bv_id'], progress['current'], progress['initial'], progress['target']
                        )

                if all_complete:
                    break

        finally:
            shutdown_handler.uninstall()

    # Stop workers
    console.print('[cyan]Stopping workers...[/cyan]')
    validator.stop()
    dispatcher.stop()
    console.print('[green]✓ Workers stopped[/green]')

    # Collect results
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
                'elapsed': progress['elapsed'],
            }
        )

    return results, validator.get_stats(), overall_start_time, shutdown_handler.is_shutdown_requested()


def print_summary(results, stats, failed_videos, bv_ids, overall_start_time, interrupted):
    """Print final summary."""
    overall_elapsed = int((datetime.now() - overall_start_time).total_seconds())
    successful_videos = [r for r in results if r['success']]

    console.print()
    summary_title = '[bold yellow]⚠ Interrupted[/bold yellow]' if interrupted else '[bold green]✓ Complete[/bold green]'
    summary_border = 'yellow' if interrupted else 'green'

    validation_rate = stats['validated'] / stats['checked'] * 100 if stats['checked'] > 0 else 0

    console.print(
        Panel.fit(
            f'[bold]Overall Summary[/bold]\n\n'
            f'[cyan]Total Time:[/cyan] {time_format(overall_elapsed)}\n'
            f'[cyan]Videos Processed:[/cyan] {len(results)}/{len(bv_ids)}\n'
            f'[cyan]Successful:[/cyan] {len(successful_videos)}\n'
            f'[cyan]Failed:[/cyan] {len(failed_videos)}\n\n'
            f'[cyan]Proxies Checked:[/cyan] {stats["checked"]}\n'
            f'[cyan]Valid Proxies:[/cyan] {stats["validated"]}\n'
            f'[cyan]Validation Rate:[/cyan] {validation_rate:.1f}%',
            title=summary_title,
            border_style=summary_border,
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


def main():
    """Main entry point."""
    # Parse arguments
    args = parse_args()

    # Get platform
    platform = get_platform(args.platform)
    console.print(f'[bold cyan]Platform: {platform.get_name()}[/bold cyan]')

    # Get video list
    video_ids = get_video_list(args, platform)
    video_ids = apply_blacklist(video_ids, args.blacklist)

    # Get proxies
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

    # Limit proxy count
    if len(total_proxies) > 10000:
        console.print('[yellow]More than 10000 proxies, randomly picking 10000[/yellow]')
        random.shuffle(total_proxies)
        total_proxies = total_proxies[:10000]

    # Prepare video boosters
    video_boosters, failed_videos = prepare_video_boosters(
        video_ids, args.increment, platform, args.cooldown, args.timeout
    )

    if not video_boosters:
        console.print('[red]No videos to process. Exiting.[/red]')
        sys.exit(1)

    # Run pipeline
    console.print('\n[bold cyan]Starting boost system[/bold cyan]')
    console.print(f'[cyan]Validators: {args.validators}, Workers: {args.workers}[/cyan]')

    results, stats, overall_start_time, interrupted = run_pipeline(args, video_boosters, total_proxies)

    # Print summary
    print_summary(results, stats, failed_videos, video_ids, overall_start_time, interrupted)


if __name__ == '__main__':
    main()
