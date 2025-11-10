#!/usr/bin/env python3
import argparse
import os
import subprocess

from fetch_author_videos import get_user_videos
from utils import load_env


def boost_all_videos(mid, increment, dry_run=False, cookies_file=None):
    """
    Boost all videos from a user

    Args:
        mid: User's mid (user ID)
        increment: View count increment per video
        dry_run: If True, only print what would be done
        cookies_file: Path to cookies file for API authentication
    """
    print(f'Fetching videos from user {mid}...')
    bvids = get_user_videos(mid, cookies_file=cookies_file)

    if not bvids:
        print('No videos found!')
        return

    print(f'\nFound {len(bvids)} videos. Will boost each by +{increment} views.\n')

    failed = []
    succeeded = []

    for i, bvid in enumerate(bvids, 1):
        print(f'[{i}/{len(bvids)}] Boosting {bvid}...')

        if dry_run:
            print(f'  [DRY RUN] Would run: uv run python booster.py {bvid} {increment}')
            succeeded.append(bvid)
            continue

        try:
            result = subprocess.run(
                ['uv', 'run', 'python', 'booster.py', bvid, str(increment)],
                capture_output=True,
                text=True,
                timeout=600,  # 10 minute timeout per video
            )

            if result.returncode == 0:
                print('  ✓ Success!')
                succeeded.append(bvid)
            else:
                print('  ✗ Failed!')
                failed.append(bvid)

        except subprocess.TimeoutExpired:
            print('  ✗ Timeout!')
            failed.append(bvid)
        except Exception as e:
            print(f'  ✗ Error: {e}')
            failed.append(bvid)

    # Summary
    print(f'\n{"=" * 60}')
    print('Boost Complete!')
    print(f'{"=" * 60}')
    print(f'Total videos: {len(bvids)}')
    print(f'Succeeded: {len(succeeded)}')
    print(f'Failed: {len(failed)}')

    if failed:
        print('\nFailed videos:')
        for bvid in failed:
            print(f'  - {bvid}')


def main():
    load_env()  # Load .env file

    parser = argparse.ArgumentParser(
        description='Boost all videos from a Bilibili user',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Boost all videos from user 123456 by +50 views each
  python boost_author.py 123456 50 --cookies cookies.txt
  
  # Dry run (don't actually boost)
  python boost_author.py 123456 50 --dry-run --cookies cookies.txt
  
  # Use .env file for configuration
  python boost_author.py  # reads BILIBILI_USER_MID and DEFAULT_INCREMENT from .env

Note: Requires cookies.txt from logged-in browser session.
      See README.md for instructions on how to export cookies.
        """,
    )

    # Get defaults from environment
    default_mid = os.getenv('BILIBILI_USER_MID')
    default_increment = os.getenv('DEFAULT_INCREMENT', '50')
    default_cookies = os.getenv('BILIBILI_COOKIES_FILE', 'cookies.txt')

    parser.add_argument(
        'mid', type=int, nargs='?' if default_mid else None, default=default_mid, help='User mid (user ID)'
    )
    parser.add_argument(
        'increment',
        type=int,
        nargs='?' if default_increment else None,
        default=int(default_increment) if default_increment else None,
        help='View count increment per video',
    )
    parser.add_argument('--dry-run', action='store_true', help='Print what would be done without doing it')
    parser.add_argument(
        '--cookies',
        '-c',
        default=default_cookies,
        help=f'Path to cookies file (Netscape format, default: {default_cookies})',
    )

    args = parser.parse_args()

    if not args.mid:
        parser.error('mid is required (either as argument or BILIBILI_USER_MID in .env)')

    if not args.increment:
        parser.error('increment is required (either as argument or DEFAULT_INCREMENT in .env)')

    if not args.cookies and not args.dry_run:
        print('⚠️  WARNING: --cookies is required for API authentication!')
        print('Use --cookies cookies.txt to provide your browser cookies.')
        print('Or set BILIBILI_COOKIES_FILE in .env file')
        print('See README.md for instructions.\n')

    boost_all_videos(args.mid, args.increment, args.dry_run, args.cookies)


if __name__ == '__main__':
    main()
