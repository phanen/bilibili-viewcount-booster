# Bilibili View Count Booster

Modified from [liqwang/bilibili-viewcount-booster](https://github.com/liqwang/bilibili-viewcount-booster) via AI.

A non-blocking pipeline tool to boost Bilibili video view counts using proxy validation.

## Installation

```shell
git clone https://github.com/your-username/bilibili-viewcount-booster
cd bilibili-viewcount-booster
uv sync
```

## Configuration

### Option 1: Using .env file (Recommended)

Create a `.env` file to store your private configuration:

```bash
cp .env.example .env
```

Edit `.env`:
```bash
# Bilibili User Configuration
BILIBILI_USER_MID=123456

# Path to cookies file (Netscape format)
BILIBILI_COOKIES_FILE=cookies.txt

# Default increment for boost operations
DEFAULT_INCREMENT=50
```

With `.env` configured, you can run commands without arguments:
```bash
# This will use values from .env
uv run python boost_author.py
uv run python fetch_author_videos.py
```

### Option 2: Command line arguments

You can always override `.env` values with command line arguments.

## Usage

### Boost a Single Video

```shell
uv run python booster.py <BVID> <INCREMENT>
```

### Fetch All Videos from an Author

```shell
# Using .env
uv run python fetch_author_videos.py

# Using command line
uv run python fetch_author_videos.py <USER_MID> --cookies cookies.txt

# Save to file
uv run python fetch_author_videos.py <USER_MID> --cookies cookies.txt --output videos.json

# Limit results
uv run python fetch_author_videos.py <USER_MID> --cookies cookies.txt --max 10
```

### Boost All Videos from an Author

```shell
# Using .env
uv run python boost_author.py

# Using command line
uv run python boost_author.py <USER_MID> <INCREMENT> --cookies cookies.txt

# Dry run (preview only)
uv run python boost_author.py <USER_MID> <INCREMENT> --dry-run
```

## How It Works
1. Fetches proxies from API and queues for validation
2. Validates proxies (75 threads) against httpbin.org
3. Uses valid proxies to boost views (50 threads)
4. Each proxy waits 5 minutes before reuse

## References

- https://github.com/xu0329/bilibili_proxy
- https://github.com/SocialSisterYi/bilibili-API-collect
- https://github.com/liqwang/bilibili-viewcount-booster

## License

MIT
