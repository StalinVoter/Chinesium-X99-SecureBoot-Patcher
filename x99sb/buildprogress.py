from __future__ import annotations


class BuildProgressTracker:
    """Map discrete Secure Boot build milestones to a monotonic 0-100 GUI value.

    The firmware build tools do not report a byte-level percentage, so these are
    deliberately pipeline milestones rather than invented UEFIReplace progress.
    """

    def __init__(self, targets: list[str] | tuple[str, ...]):
        self.targets = list(targets)
        self.completed_targets: set[str] = set()
        self.current_percent = 0

    def update(self, state: str, text: str) -> int:
        percent = self.current_percent
        if state == 'PASS' and text.startswith('Input inspected:'):
            percent = max(percent, 10)
        elif state == 'PASS' and text.startswith('Auto plan:'):
            percent = max(percent, 15)
        elif state == 'RUNNING' and text.startswith('Update '):
            percent = max(percent, 15)
        elif state == 'PASS':
            matched = next((name for name in self.targets if text.startswith(name + ':')), None)
            if matched is not None:
                self.completed_targets.add(matched)
                total = max(1, len(self.targets))
                percent = max(percent, 15 + round(60 * len(self.completed_targets) / total))
            elif text.startswith('Final Secure Boot 2023 validation passed'):
                percent = max(percent, 95)
            elif text.startswith('Output size preserved:'):
                percent = 100
        self.current_percent = min(100, max(0, int(percent)))
        return self.current_percent
