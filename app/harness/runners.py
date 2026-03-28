from __future__ import annotations

import json
import subprocess
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Thread
from typing import Any, TextIO

from app.harness.models import RunnerResult
from app.harness.protocols import EventBrokerProtocol
from app.models import Run, Task, TaskEvent


class CodexRunner:
    """Run Codex non-interactively and translate its output into task artifacts."""

    def __init__(self, binary: str = "codex") -> None:
        self.binary = binary

    def execute(self, task: Task, run: Run, broker: EventBrokerProtocol) -> RunnerResult:
        """Execute Codex for a task and return a generic runner result."""
        cwd = Path(run.cwd)
        self._publish_log(task.id, "Launching Codex CLI", broker)
        return self._run_codex(cwd, run.structured_prompt, task.id, broker)

    def _run_codex(
        self,
        cwd: Path,
        prompt: str,
        task_id: str,
        broker: EventBrokerProtocol,
    ) -> RunnerResult:
        """Invoke `codex exec --json` and capture both streamed logs and final output."""
        with NamedTemporaryFile(mode="w+", encoding="utf-8", suffix=".txt") as output_file:
            command = [
                self.binary,
                "exec",
                "--json",
                "--skip-git-repo-check",
                "--sandbox",
                "workspace-write",
                "--cd",
                str(cwd),
                "--output-last-message",
                output_file.name,
                prompt,
            ]
            process = subprocess.Popen(
                command,
                cwd=str(cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                bufsize=1,
            )

            stdout_lines: list[str] = []
            stderr_lines: list[str] = []
            stdout_thread = Thread(
                target=self._consume_stream,
                args=(process.stdout, stdout_lines, task_id, "log", broker),
                daemon=True,
            )
            stderr_thread = Thread(
                target=self._consume_stream,
                args=(process.stderr, stderr_lines, task_id, "error", broker),
                daemon=True,
            )
            stdout_thread.start()
            stderr_thread.start()

            exit_code = process.wait()
            stdout_thread.join()
            stderr_thread.join()

            output_file.seek(0)
            summary = output_file.read().strip()
            if not summary:
                summary = (
                    "Execution completed. Awaiting approval before changes are applied."
                    if exit_code == 0
                    else "Codex execution failed."
                )

        files_modified = self._collect_changed_files(cwd) if exit_code == 0 else []
        return RunnerResult(
            exit_code=exit_code,
            summary=summary,
            stdout=stdout_lines,
            stderr=stderr_lines,
            files_modified=files_modified,
        )

    def _consume_stream(
        self,
        stream: TextIO | None,
        sink: list[str],
        task_id: str,
        event_type: str,
        broker: EventBrokerProtocol,
    ) -> None:
        if stream is None:
            return
        try:
            for raw_line in stream:
                line = raw_line.rstrip()
                if not line:
                    continue
                sink.append(line)
                message = self._format_stream_message(line)
                broker.publish(TaskEvent(task_id=task_id, type=event_type, message=message))
        finally:
            stream.close()

    def _format_stream_message(self, line: str) -> str:
        try:
            payload: dict[str, Any] = json.loads(line)
        except json.JSONDecodeError:
            return line

        event_type = payload.get("type")
        if event_type == "agent_reasoning":
            return str(payload.get("text", "agent reasoning"))
        if event_type == "agent_message":
            message = payload.get("message")
            if isinstance(message, dict):
                return str(message.get("content", line))
        if event_type == "exec_command_begin":
            command = payload.get("command", [])
            if isinstance(command, list):
                return f"Running command: {' '.join(str(item) for item in command)}"
        if event_type == "exec_command_output_delta":
            return str(payload.get("chunk", line))
        if event_type == "task_complete":
            return str(payload.get("last_agent_message", "Task complete"))
        return line

    def _collect_changed_files(self, cwd: Path) -> list[str]:
        result = subprocess.run(
            ["git", "status", "--short"],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return []

        files: list[str] = []
        for line in result.stdout.splitlines():
            if not line.strip():
                continue
            files.append(line[3:] if len(line) > 3 else line)
        return sorted(set(files))

    def _publish_log(self, task_id: str, message: str, broker: EventBrokerProtocol) -> None:
        broker.publish(TaskEvent(task_id=task_id, type="log", message=message))
