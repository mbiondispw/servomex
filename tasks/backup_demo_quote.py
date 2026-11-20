"""CCI wrapper for scripts/demo/backup_demo_quote.py (the NordicGas AS backup demo quote)."""

import subprocess
import sys
from pathlib import Path

try:
    from cumulusci.core.exceptions import CommandException
    from cumulusci.core.tasks import BaseTask
    from cumulusci.core.utils import process_bool_arg
except ImportError:
    BaseTask = object
    CommandException = Exception

    def process_bool_arg(value):
        return str(value).lower() in ("true", "1", "yes")

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "demo" / "backup_demo_quote.py"


class CreateBackupDemoQuote(BaseTask):
    """Create, or reset to Draft, the NordicGas AS backup demo Quote."""

    salesforce_task = True
    task_options = {
        "dry_run": {
            "description": "Read the org and print what a real run would do, writing nothing. Default false.",
            "required": False,
        },
    }

    def _run_task(self):
        # The script authenticates through the sf CLI, so it gets the username, never a token.
        command = [sys.executable, str(SCRIPT), "--org", self.org_config.username]
        if process_bool_arg(self.options.get("dry_run") or False):
            command.append("--dry-run")
        result = subprocess.run(command, capture_output=True, text=True)
        for line in result.stdout.splitlines():
            self.logger.info(line)
        for line in result.stderr.splitlines():
            self.logger.error(line)
        if result.returncode != 0:
            raise CommandException(f"backup demo quote failed (exit {result.returncode})")
