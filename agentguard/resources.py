"""Resource control (P7): timeout, output cap, process-tree kill, audit.

Windows ref impl enforces timeout + output size strictly; memory/process-count
are best-effort via psutil here and strict via cgroups on Linux (P8).
Every violation audits RESOURCE_LIMIT and terminates the tree (P6 enforcement).
"""
from __future__ import annotations
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import List, Sequence

try:
    import psutil  # type: ignore
except Exception:
    psutil = None  # type: ignore


@dataclass
class ResourceLimits:
    timeout_seconds: int = 60
    max_output_bytes: int = 10 * 1024 * 1024
    max_memory_mb: int | None = None
    max_processes: int = 64

    def validate(self) -> None:
        if not (1 <= self.timeout_seconds <= 3600):
            raise ValueError("resources.timeout_seconds must be 1..3600 (fail-closed)")
        if not (1024 <= self.max_output_bytes <= 256 * 1024 * 1024):
            raise ValueError("resources.max_output_bytes must be 1KiB..256MiB (fail-closed)")
        if self.max_memory_mb is not None and not (16 <= self.max_memory_mb <= 65536):
            raise ValueError("resources.max_memory_mb must be 16..65536 (fail-closed)")
        if not (1 <= self.max_processes <= 1024):
            raise ValueError("resources.max_processes must be 1..1024 (fail-closed)")


class ResourceViolation(PermissionError):
    def __init__(self, reason: str):
        super().__init__(f"AGENTGUARD RESOURCE_LIMIT: {reason}")
        self.reason = reason


def _kill_tree(proc: subprocess.Popen) -> None:
    try:
        if psutil is not None:
            root = psutil.Process(proc.pid)
            for child in root.children(recursive=True):
                try:
                    child.kill()
                except Exception:
                    pass
    except Exception:
        pass
    try:
        proc.kill()
    except Exception:
        pass


def _tree_stats(proc: subprocess.Popen) -> tuple[int, int]:
    """Return (process_count, peak_rss_bytes) best-effort."""
    if psutil is None:
        return 1, 0
    try:
        root = psutil.Process(proc.pid)
        kids = root.children(recursive=True)
        rss = 0
        for p in [root, *kids]:
            try:
                rss += p.memory_info().rss
            except Exception:
                pass
        return 1 + len(kids), rss
    except Exception:
        return 1, 0


def run_guarded(cmd: Sequence[str] | str, limits: ResourceLimits,
                log_fn=None, shell: bool = False) -> subprocess.CompletedProcess:
    """Run cmd with timeout/output/process/memory guards. Raises ResourceViolation."""
    limits.validate()
    start = time.time()
    proc = subprocess.Popen(cmd, shell=shell, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, bufsize=65536)
    # Streaming drain thread: without this, a chatty child fills the OS pipe
    # buffer and hangs forever instead of tripping the output cap.
    chunks: List[str] = []
    total = [0]
    done = threading.Event()

    def _drain() -> None:
        try:
            assert proc.stdout is not None
            while True:
                data = proc.stdout.read(65536)
                if not data:
                    break
                chunks.append(data)
                total[0] += len(data)
        except Exception:
            pass
        finally:
            done.set()

    t = threading.Thread(target=_drain, daemon=True)
    t.start()
    try:
        while True:
            elapsed = time.time() - start
            if total[0] > limits.max_output_bytes:
                _kill_tree(proc)
                if log_fn:
                    log_fn("RESOURCE_LIMIT", str(cmd)[:200], "output-limit")
                raise ResourceViolation(f"output exceeded {limits.max_output_bytes} bytes (truncated)")
            if elapsed > limits.timeout_seconds:
                _kill_tree(proc)
                if log_fn:
                    log_fn("RESOURCE_LIMIT", str(cmd)[:200], "timeout")
                raise ResourceViolation(f"timeout after {limits.timeout_seconds}s")
            nproc, rss = _tree_stats(proc)
            if nproc > limits.max_processes:
                _kill_tree(proc)
                if log_fn:
                    log_fn("RESOURCE_LIMIT", str(cmd)[:200], "process-limit")
                raise ResourceViolation(f"process limit {limits.max_processes} exceeded")
            if limits.max_memory_mb is not None and rss > limits.max_memory_mb * 1024 * 1024:
                _kill_tree(proc)
                if log_fn:
                    log_fn("RESOURCE_LIMIT", str(cmd)[:200], "memory-limit")
                raise ResourceViolation(f"memory limit {limits.max_memory_mb}MiB exceeded")
            if proc.poll() is not None and done.is_set():
                break
            if proc.poll() is not None:
                done.wait(0.5)
                break
            time.sleep(0.05)
    finally:
        if proc.poll() is None:
            _kill_tree(proc)
    t.join(timeout=5)
    out = "".join(chunks)
    if len(out) > limits.max_output_bytes:
        if log_fn:
            log_fn("RESOURCE_LIMIT", str(cmd)[:200], "output-limit")
        raise ResourceViolation(f"output exceeded {limits.max_output_bytes} bytes (truncated)")
    return subprocess.CompletedProcess(cmd, proc.returncode or 0, out, "")


def limits_from_policy(policy: dict) -> ResourceLimits:
    r = (policy or {}).get("resources", {}) or {}
    lim = ResourceLimits(
        timeout_seconds=int(r.get("timeout_seconds", 60)),
        max_output_bytes=int(r.get("max_output_bytes", 10 * 1024 * 1024)),
        max_memory_mb=r.get("max_memory_mb", None),
        max_processes=int(r.get("max_processes", 64)),
    )
    lim.validate()
    return lim
