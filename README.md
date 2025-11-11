# Bilibili View Count Booster

Modified from [liqwang/bilibili-viewcount-booster](https://github.com/liqwang/bilibili-viewcount-booster) via AI.

A non-blocking pipeline tool to boost Bilibili video view counts using proxy validation.

1. Fetches proxies from API and queues for validation
2. Validates proxies (75 threads) against httpbin.org
3. Uses valid proxies to boost views (50 threads)
4. Each proxy waits 5 minutes before reuse

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
