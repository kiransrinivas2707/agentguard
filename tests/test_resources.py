"""P7 resource-limit tests: timeout, output cap, tree kill, audit, validation."""
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from agentguard.policy import load_policy, PolicyEngine
from agentguard.resources import ResourceLimits, ResourceViolation, run_guarded
from agentguard.sandbox import GuardedSandbox


def test_cpu_timeout_terminates():
    lim = ResourceLimits(timeout_seconds=1)
    t0 = time.time()
    with pytest.raises(ResourceViolation):
        run_guarded([sys.executable, "-c", "import time; time.sleep(30)"], lim)
    assert time.time() - t0 < 10


def test_execution_timeout_via_sandbox(tmp_path):
    sb = GuardedSandbox(PolicyEngine(load_policy("agentguard.yaml")),
                        log_path=tmp_path / "a.jsonl")
    with pytest.raises(PermissionError, match="RESOURCE_LIMIT"):
        sb.run_command([sys.executable, "-c", "import time; time.sleep(30)"], timeout=1)
    assert "RESOURCE_LIMIT" in (tmp_path / "a.jsonl").read_text()


def test_output_limit_truncates():
    lim = ResourceLimits(timeout_seconds=20, max_output_bytes=1024)
    with pytest.raises(ResourceViolation, match="output exceeded"):
        run_guarded([sys.executable, "-c", "print('x'*100000)"], lim)


def test_process_tree_terminated():
    lim = ResourceLimits(timeout_seconds=2)
    with pytest.raises(ResourceViolation):
        run_guarded([sys.executable, "-c",
                     "import subprocess,sys,time;subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)']);time.sleep(30)"],
                    lim)


def test_resource_violation_audited(tmp_path):
    sb = GuardedSandbox(PolicyEngine(load_policy("agentguard.yaml")),
                        log_path=tmp_path / "a.jsonl")
    with pytest.raises(PermissionError):
        sb.run_command([sys.executable, "-c", "print('y'*50000)"],
                       limits=ResourceLimits(timeout_seconds=20, max_output_bytes=1024))
    blob = (tmp_path / "a.jsonl").read_text()
    assert "RESOURCE_LIMIT" in blob


def test_bad_limits_fail_closed():
    with pytest.raises(ValueError):
        ResourceLimits(timeout_seconds=0).validate()
    with pytest.raises(ValueError):
        ResourceLimits(max_output_bytes=10).validate()
