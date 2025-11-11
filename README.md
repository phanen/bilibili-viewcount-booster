# Bilibili View Count Booster

Modified from [liqwang/bilibili-viewcount-booster](https://github.com/liqwang/bilibili-viewcount-booster) via AI.

A non-blocking pipeline tool to boost Bilibili video view counts using validated proxies.

## How It Works

This tool simulates video views by sending HTTP POST requests to Bilibili's video playback API through validated proxy servers:

1. **Fetch Proxies** - Downloads free proxy lists from public sources
2. **Validate Proxies** - Tests each proxy against httpbin.org to filter working ones
3. **Boost Views** - Sends video view requests through valid proxies
4. **Cooldown Management** - Each proxy waits 5 minutes before reuse to avoid rate limiting

## Installation

```shell
git clone https://github.com/your-username/bilibili-viewcount-booster
cd bilibili-viewcount-booster
uv sync
uv run python scripts/booster.py --mid <USER_MID> --increment <INCREMENT> --cookies cookies.txt
```

## References

- https://github.com/xu0329/bilibili_proxy
- https://github.com/SocialSisterYi/bilibili-API-collect
- https://github.com/liqwang/bilibili-viewcount-booster

## License

MIT
