"""P8 runtime tests: Linux detection + Docker anti-escape validation."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentguard.runtime import linux_features, validate_docker_run


def test_linux_features_shape():
    r = linux_features()
    assert set(r["features"]) == {"namespaces", "capabilities", "seccomp", "landlock", "cgroups"}


def test_docker_privileged_rejected():
    ok, reasons = validate_docker_run({"privileged": True, "volumes": ["./ws:/ws"]})
    assert not ok and any("privileged" in x for x in reasons)


def test_docker_host_modes_rejected():
    ok, _ = validate_docker_run({"network_mode": "host"})
    assert not ok
    ok, _ = validate_docker_run({"pid_mode": "host"})
    assert not ok


def test_docker_socket_and_proc_rejected():
    ok, r1 = validate_docker_run({"volumes": ["/var/run/docker.sock:/var/run/docker.sock"]})
    ok2, r2 = validate_docker_run({"volumes": ["/proc:/host/proc"]})
    assert not ok and not ok2


def test_docker_caps_rejected_and_clean_passes():
    ok, _ = validate_docker_run({"cap_add": ["SYS_ADMIN"]})
    assert not ok
    ok, reasons = validate_docker_run({"volumes": ["./workspace:/workspace:ro"]})
    assert ok, reasons
