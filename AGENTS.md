# Development Guide

## Architecture

```
scripts/
├── booster.py              # Main entry point
├── signal_handler.py       # Graceful shutdown handling
├── executor.py             # Proxy validation & video boosting
├── progress_tracker.py     # Progress display (rich/CI)
├── utils.py                # Utility functions
└── fetch_author_videos.py  # User video fetching
```

## Development

1. **Make changes**
2. **Format code**: `ruff format scripts/`
3. **Check linting**: `ruff check scripts/`
4. **Test**: `python scripts/booster.py --bv BV15Z421T7pE -n 10`

## Code Style

- No global state
- Single responsibility per function
- Functions < 80 lines
- Type hints preferred
- Minimal comments (self-documenting code)

## Testing

```bash
# Quick test
python scripts/booster.py --bv BV15Z421T7pE -n 10 --validators 5 --workers 3
# Test graceful shutdown
# Run above, then press Ctrl-C once (graceful) or twice (force)
```

## Notes

- All CLI arguments are backward compatible
- Signal handler is reusable across projects
- Progress tracker abstraction allows easy UI changes
- Executor module handles all threading complexity
