# Multi-Platform View Count Booster

Modified from [liqwang/bilibili-viewcount-booster](https://github.com/liqwang/bilibili-viewcount-booster) via AI.

A non-blocking pipeline tool to boost video view counts on multiple platforms using validated proxies.

## Supported Platforms

- **Bilibili** (哔哩哔哩) - Full support including user video fetching
- **Xiaohongshu** (小红书 / Little Red Book) - Basic support for note views

## How It Works

This tool simulates video views by sending HTTP requests to platform APIs through validated proxy servers:

1. **Fetch Proxies** - Downloads free proxy lists from public sources
2. **Validate Proxies** - Tests each proxy against httpbin.org to filter working ones
3. **Boost Views** - Sends video view requests through valid proxies
4. **Cooldown Management** - Each proxy waits 5 minutes before reuse to avoid rate limiting

## Installation

```shell
git clone https://github.com/your-username/bilibili-viewcount-booster
cd bilibili-viewcount-booster
uv sync
```

## Usage

### Bilibili Examples

```shell
# Single video
uv run python scripts/booster.py --platform bilibili --video-ids BV1xxx --increment 1000

# Multiple videos
uv run python scripts/booster.py --platform bilibili --video-ids BV1xxx BV2yyy -n 100

# All videos from a user (requires cookies)
uv run python scripts/booster.py --platform bilibili --user-id 123456 -n 50 --cookies cookies.txt

# Backward compatibility (defaults to Bilibili)
uv run python scripts/booster.py --bvids BV1xxx --increment 1000
```

### Xiaohongshu Examples

```shell
# Single note
uv run python scripts/booster.py --platform xiaohongshu --video-ids 63f9a8b0000000001f03e6a1 -n 100

# Multiple notes
uv run python scripts/booster.py --platform xhs --video-ids note1 note2 note3 -n 50
```

## Platform-Specific Notes

### Bilibili
- Fully supported with view count tracking
- Supports fetching all videos from a user with `--user-id` (requires cookies)
- View count changes are reflected in real-time

### Xiaohongshu
- Basic implementation for note view boosting
- View count tracking not available (platform limitation)
- User video fetching not yet implemented - use `--video-ids` directly
- May require authentication cookies for production use

## References

- https://github.com/xu0329/bilibili_proxy
- https://github.com/SocialSisterYi/bilibili-API-collect
- https://github.com/liqwang/bilibili-viewcount-booster

## License

MIT
