"""
Signal handling module for graceful shutdown.
Handles Ctrl-C (SIGINT) with a two-stage approach:
- First Ctrl-C: Graceful shutdown
- Second Ctrl-C: Immediate force quit
"""

import signal
import sys

from rich.console import Console

console = Console()


class ShutdownHandler:
    """Manages graceful shutdown on SIGINT (Ctrl-C)."""

    def __init__(self):
        self.shutdown_requested = False
        self._original_sigint = None

    def install(self):
        """Install the signal handler."""
        self._original_sigint = signal.signal(signal.SIGINT, self._handle_signal)

    def uninstall(self):
        """Restore original signal handler."""
        if self._original_sigint:
            signal.signal(signal.SIGINT, self._original_sigint)

    def _handle_signal(self, sig, frame):
        """Handle SIGINT signal."""
        if self.shutdown_requested:
            console.print('\n[red]Force quit detected. Exiting immediately...[/red]')
            sys.exit(1)

        console.print('\n[yellow]⚠ Shutdown requested (Ctrl-C detected). Stopping gracefully...[/yellow]')
        console.print('[yellow]Press Ctrl-C again to force quit.[/yellow]')
        self.shutdown_requested = True

    def is_shutdown_requested(self):
        """Check if shutdown was requested."""
        return self.shutdown_requested

    def __enter__(self):
        """Context manager entry."""
        self.install()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.uninstall()
        return False


# Global instance for convenience
_global_handler = None


def get_shutdown_handler():
    """Get or create the global shutdown handler."""
    global _global_handler
    if _global_handler is None:
        _global_handler = ShutdownHandler()
    return _global_handler


def is_shutdown_requested():
    """Check if shutdown was requested (convenience function)."""
    return get_shutdown_handler().is_shutdown_requested()
