import argparse
import json
import os
import time
import urllib.parse
from functools import reduce
from hashlib import md5

import requests
from utils import load_env

# WBI signing constants
MIXIN_KEY_ENC_TAB = [
    46,
    47,
    18,
    2,
    53,
    8,
    23,
    32,
    15,
    50,
    10,
    31,
    58,
    3,
    45,
    35,
    27,
    43,
    5,
    49,
    33,
    9,
    42,
    19,
    29,
    28,
    14,
    39,
    12,
    38,
    41,
    13,
    37,
    48,
    7,
    16,
    24,
    55,
    40,
    61,
    26,
    17,
    0,
    1,
    60,
    51,
    30,
    4,
    22,
    25,
    54,
    21,
    56,
    59,
    6,
    63,
    57,
    62,
    11,
    36,
    20,
    34,
    44,
    52,
]


def get_mixin_key(orig: str):
    """对 imgKey 和 subKey 进行字符顺序打乱编码"""
    return reduce(lambda s, i: s + orig[i], MIXIN_KEY_ENC_TAB, '')[:32]


def enc_wbi(params: dict, img_key: str, sub_key: str):
    """为请求参数进行 wbi 签名"""
    mixin_key = get_mixin_key(img_key + sub_key)
    curr_time = round(time.time())
    params['wts'] = curr_time
    params = dict(sorted(params.items()))
    # 过滤 value 中的 "!'()*" 字符
    params = {k: ''.join(filter(lambda chr: chr not in "!'()*", str(v))) for k, v in params.items()}
    query = urllib.parse.urlencode(params)
    wbi_sign = md5((query + mixin_key).encode()).hexdigest()
    params['w_rid'] = wbi_sign
    return params


def get_wbi_keys(session: requests.Session):
    """获取最新的 img_key 和 sub_key"""
    resp = session.get('https://api.bilibili.com/x/web-interface/nav')
    resp.raise_for_status()
    json_content = resp.json()
    img_url = json_content['data']['wbi_img']['img_url']
    sub_url = json_content['data']['wbi_img']['sub_url']
    img_key = img_url.rsplit('/', 1)[1].split('.')[0]
    sub_key = sub_url.rsplit('/', 1)[1].split('.')[0]
    return img_key, sub_key


def init_session():
    """初始化会话并获取必要的cookies"""
    session = requests.Session()
    session.headers.update(
        {
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/120.0.0.0 Safari/537.36'
            ),
            'Referer': 'https://www.bilibili.com/',
            'Origin': 'https://www.bilibili.com',
        }
    )

    # 访问主页获取 cookies (包括 buvid3 等)
    try:
        session.get('https://www.bilibili.com/', timeout=10)
        time.sleep(1)
    except Exception as e:
        print(f'Warning: Failed to initialize cookies: {e}')

    return session


def get_user_videos(mid, max_videos=None, cookies_file=None):
    """
    Fetch all video BVIDs from a Bilibili user

    Args:
        mid: User's mid (user ID)
        max_videos: Maximum number of videos to fetch (None for all)
        cookies_file: Path to cookies file (Netscape format) - REQUIRED to bypass anti-bot

    Returns:
        List of BVIDs
    """
    # Initialize session with cookies
    session = init_session()

    # Load cookies from file if provided
    if cookies_file:
        try:
            from http.cookiejar import MozillaCookieJar

            cookie_jar = MozillaCookieJar(cookies_file)
            cookie_jar.load(ignore_discard=True, ignore_expires=True)
            session.cookies.update(cookie_jar)
            print(f'Loaded cookies from {cookies_file}')
        except Exception as e:
            print(f'Warning: Failed to load cookies from {cookies_file}: {e}')
            print('NOTE: API may be blocked without valid cookies. See README for instructions.')
    else:
        print('WARNING: No cookies file provided. API requests may be blocked by anti-bot measures.')
        print('Please provide cookies with --cookies option. See README for instructions.')

    # Get WBI keys for signing
    print('Getting WBI keys...')
    try:
        img_key, sub_key = get_wbi_keys(session)
        print(f'WBI keys obtained: img_key={img_key[:8]}..., sub_key={sub_key[:8]}...')
    except Exception as e:
        print(f'Error getting WBI keys: {e}')
        return []

    bvids = []
    page = 1
    ps = 50  # items per page

    while True:
        url = 'https://api.bilibili.com/x/space/wbi/arc/search'

        # Prepare params with WBI signing
        params = {
            'mid': str(mid),
            'pn': str(page),
            'ps': str(ps),
            'order': 'pubdate',
            'platform': 'web',
            'web_location': '1550101',
        }

        # Sign the params
        signed_params = enc_wbi(params, img_key, sub_key)

        try:
            response = session.get(url, params=signed_params, timeout=30)
            data = response.json()

            if data['code'] != 0:
                print(f'Error: {data["message"]} (code: {data["code"]})')
                if data['code'] == -352:
                    print('\n⚠️  Anti-bot protection detected!')
                    print('You need to provide cookies from a logged-in browser session.')
                    print('See README.md for instructions on how to export cookies.\n')
                break

            vlist = data['data']['list']['vlist']

            if not vlist:
                break

            for video in vlist:
                bvids.append(video['bvid'])
                if max_videos and len(bvids) >= max_videos:
                    return bvids[:max_videos]

            # Check if there are more pages
            page_info = data['data']['page']
            if page * ps >= page_info['count']:
                break

            page += 1
            time.sleep(1)  # Be nice to the API

        except Exception as e:
            print(f'Error fetching page {page}: {e}')
            break

    return bvids


def main():
    load_env()  # Load .env file

    parser = argparse.ArgumentParser(
        description='Fetch all video BVIDs from a Bilibili user',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Note: Due to Bilibili's anti-bot measures, you need to provide cookies 
from a logged-in browser session using the --cookies option.

To export cookies:
1. Install "Get cookies.txt LOCALLY" browser extension
2. Visit bilibili.com while logged in
3. Click the extension and save cookies.txt
4. Use: --cookies path/to/cookies.txt

Or set BILIBILI_COOKIES_FILE in .env file
        """,
    )

    # Get defaults from environment
    default_mid = os.getenv('BILIBILI_USER_MID')
    default_cookies = os.getenv('BILIBILI_COOKIES_FILE', 'cookies.txt')

    parser.add_argument(
        'mid', type=int, nargs='?' if default_mid else None, default=default_mid, help='User mid (user ID)'
    )
    parser.add_argument('--max', type=int, help='Maximum number of videos to fetch')
    parser.add_argument('--output', '-o', help='Output file (JSON format)')
    parser.add_argument(
        '--cookies',
        '-c',
        default=default_cookies,
        help=f'Path to cookies file (Netscape format, default: {default_cookies})',
    )

    args = parser.parse_args()

    if not args.mid:
        parser.error('mid is required (either as argument or in .env file)')

    print(f'Fetching videos from user {args.mid}...')
    bvids = get_user_videos(args.mid, args.max, args.cookies)

    print(f'\nFound {len(bvids)} videos:')
    for bvid in bvids:
        print(f'  - {bvid}')

    if args.output:
        with open(args.output, 'w') as f:
            json.dump({'mid': args.mid, 'bvids': bvids}, f, indent=2)
        print(f'\nSaved to {args.output}')

    return bvids


if __name__ == '__main__':
    main()
