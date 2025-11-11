"""Progress tracking abstraction for different display modes."""

import os
from abc import ABC, abstractmethod
from contextlib import contextmanager

from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn


class ProgressTracker(ABC):
    """Abstract base class for progress tracking."""

    def __init__(self):
        self.fetch_task = None
        self.validate_task = None
        self.consume_task = None
        self.video_task = None

    @abstractmethod
    def create_tasks(self, total_proxies, increment_target, bv, bv_ids, video_idx):
        """Create progress tracking tasks."""
        pass

    @abstractmethod
    def update_fetch(self, completed, total, status):
        """Update fetch progress."""
        pass

    @abstractmethod
    def update_validate(self, checked, valid):
        """Update validation progress."""
        pass

    @abstractmethod
    def update_consume(self, current, initial, target, hits):
        """Update consumption progress."""
        pass

    @abstractmethod
    def update_status(self, current, initial, target, hits):
        """Update status (for periodic checks)."""
        pass

    @abstractmethod
    def mark_complete(self, current, initial, target, bv, video_idx):
        """Mark as complete."""
        pass

    @abstractmethod
    def finalize(self, fetched_count, checked_count, validated_count, current, target):
        """Finalize progress display."""
        pass

    @abstractmethod
    @contextmanager
    def progress_context(self):
        """Context manager for progress tracking."""
        pass


class RichProgressTracker(ProgressTracker):
    """Rich progress bars for interactive terminals."""

    def __init__(self):
        super().__init__()
        self.console = Console()
        self.progress = None
        self.video_progress = {}  # {bv_id: task_id}

    @contextmanager
    def progress_context(self):
        """Create rich progress context."""
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn('[progress.description]{task.description}'),
            BarColumn(),
            TaskProgressColumn(),
            TextColumn('[cyan]{task.fields[status]}[/cyan]'),
            console=self.console,
            transient=False,
        )
        with self.progress as p:
            yield p

    def add_video_task(self, bv, increment_target, initial_view):
        """Add a new video task to the progress tracker."""
        if self.progress:
            task_id = self.progress.add_task(
                f'[green]{bv}', total=increment_target, status=f'Starting (Initial: {initial_view})'
            )
            self.video_progress[bv] = task_id
            return task_id
        return None

    def update_video_progress(self, bv, current, initial, target, hits):
        """Update progress for a specific video."""
        if self.progress and bv in self.video_progress:
            current_increment = current - initial
            self.progress.update(
                self.video_progress[bv],
                completed=min(current_increment, target),
                status=f'Views: {current} (+{current_increment}), Hits: {hits}',
            )

    def mark_video_complete(self, bv, current, initial, target):
        """Mark a video as complete."""
        if self.progress and bv in self.video_progress:
            current_increment = current - initial
            self.progress.update(
                self.video_progress[bv], completed=target, status=f'✓ Done! {current} (+{current_increment})'
            )

    def create_tasks(self, total_proxies, increment_target, bv, bv_ids, video_idx):
        """Create rich progress tasks."""
        if len(bv_ids) > 1:
            self.video_task = self.progress.add_task(
                '[magenta]Processing videos',
                total=len(bv_ids),
                status=f'Video {video_idx}/{len(bv_ids)}: {bv}',
            )

        self.fetch_task = self.progress.add_task('[yellow]Fetching proxies', total=total_proxies, status='')
        self.validate_task = self.progress.add_task('[blue]Validating proxies', total=None, status='')
        self.consume_task = self.progress.add_task(
            f'[green]Boosting {bv}', total=increment_target, status=f'Target: +{increment_target}'
        )

    def update_fetch(self, completed, total, status):
        """Update fetch progress."""
        if self.progress and self.fetch_task:
            self.progress.update(self.fetch_task, completed=completed, status=status)

    def update_validate(self, checked, valid):
        """Update validation progress."""
        if self.progress and self.validate_task:
            self.progress.update(self.validate_task, completed=checked, status=f'Checked: {checked}, Valid: {valid}')

    def update_consume(self, current, initial, target, hits):
        """Update consumption progress."""
        if self.progress and self.consume_task:
            current_increment = current - initial
            self.progress.update(
                self.consume_task,
                completed=min(current_increment, target),
                status=f'Current: {current} (+{current_increment}), Hits: {hits}',
            )

    def update_status(self, current, initial, target, hits):
        """Update status (same as update_consume for rich display)."""
        self.update_consume(current, initial, target, hits)

    def mark_complete(self, current, initial, target, bv, video_idx):
        """Mark as complete."""
        current_increment = current - initial
        if self.progress and self.consume_task:
            self.progress.update(
                self.consume_task, completed=target, status=f'✓ Target reached! {current} (+{current_increment})'
            )
        if self.video_task is not None and self.progress:
            self.progress.update(self.video_task, completed=video_idx, status=f'✓ {bv} complete')

    def finalize(self, fetched_count, checked_count, validated_count, current, target):
        """Finalize progress display."""
        if self.progress:
            if self.fetch_task:
                self.progress.update(
                    self.fetch_task, completed=fetched_count, status=f'✓ Complete. Fetched: {fetched_count}'
                )
            if self.validate_task:
                self.progress.update(
                    self.validate_task,
                    completed=checked_count,
                    status=f'✓ Done. Checked: {checked_count}, Valid: {validated_count}',
                )
            if self.consume_task:
                self.progress.update(
                    self.consume_task, completed=min(current, target), status=f'✓ Done. Views: {current}'
                )


class CIProgressTracker(ProgressTracker):
    """Simple text logging for CI environments."""

    def __init__(self):
        super().__init__()
        self.video_progress = {}
        self.last_fetch_status = None
        self.last_validate_log = 0
        self.last_consume_log = 0
        print('[CI] Starting pipeline (CI mode - simplified logging)', flush=True)

    @contextmanager
    def progress_context(self):
        """Dummy context for CI mode."""
        from contextlib import nullcontext

        with nullcontext():
            yield None

    def add_video_task(self, bv, increment_target, initial_view):
        """Add a new video task."""
        self.video_progress[bv] = {'target': increment_target, 'initial': initial_view}
        print(f'[CI] Video {bv}: Starting (Initial: {initial_view}, Target: +{increment_target})', flush=True)

    def update_video_progress(self, bv, current, initial, target, hits):
        """Update progress for a specific video."""
        current_increment = current - initial
        if current_increment % 10 == 0 or current_increment >= target:
            print(
                f'[CI] {bv}: Views={current} (+{current_increment}/{target}), Hits={hits}',
                flush=True,
            )

    def mark_video_complete(self, bv, current, initial, target):
        """Mark a video as complete."""
        current_increment = current - initial
        print(f'[CI] {bv}: ✓ Complete! {current} (+{current_increment})', flush=True)

    def create_tasks(self, total_proxies, increment_target, bv, bv_ids, video_idx):
        """No tasks needed for CI mode."""
        pass

    def update_fetch(self, completed, total, status):
        """Log fetch progress (only when status changes)."""
        if status != self.last_fetch_status:
            if completed == total:
                print(f'[CI] Fetched: {completed}/{total}', flush=True)
            elif 'recycling' in status.lower():
                print('[CI] All proxies fetched, recycling...', flush=True)
            self.last_fetch_status = status

    def update_validate(self, checked, valid):
        """Log validation progress (throttled)."""
        if checked % 100 == 0 and checked != self.last_validate_log:
            print(f'[CI] Validation: Checked={checked}, Valid={valid}', flush=True)
            self.last_validate_log = checked

    def update_consume(self, current, initial, target, hits):
        """Log consumption progress (throttled)."""
        if hits % 10 == 0 and hits != self.last_consume_log:
            print(f'[CI] Consuming: Hits={hits}', flush=True)
            self.last_consume_log = hits

    def update_status(self, current, initial, target, hits):
        """Log status check (always logged in CI)."""
        current_increment = current - initial
        print(
            f'[CI] Status: Views={current} (+{current_increment}/{target}), Hits={hits}',
            flush=True,
        )

    def mark_complete(self, current, initial, target, bv, video_idx):
        """Mark as complete."""
        current_increment = current - initial
        print(f'[CI] ✓ Target reached! {bv}: {current} (+{current_increment})', flush=True)

    def finalize(self, fetched_count, checked_count, validated_count, current, target):
        """Finalize (no-op for CI)."""
        pass


def get_progress_tracker(style='auto'):
    """Factory function to get appropriate progress tracker.

    Args:
        style: 'auto' (detect from CI env), 'rich' (fancy bars), 'ci' (simple logging)
    """
    if style == 'auto':
        is_ci = os.getenv('CI', '').lower() in ('true', '1', 'yes')
        return CIProgressTracker() if is_ci else RichProgressTracker()
    elif style == 'ci':
        return CIProgressTracker()
    else:  # 'rich'
        return RichProgressTracker()
