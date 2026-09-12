"""Exercise the trusted supervisor launch contract without cloud credentials."""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _script_import_path(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "infra/sim-worker"))


def _bootstrap():
    spec = importlib.util.spec_from_file_location(
        "sim_bootstrap", ROOT / "infra/sim-worker/bootstrap.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_launch_passes_only_env_file_to_trusted_parent():
    module = _bootstrap()
    image = "example.azurecr.io/lunaris-sim-worker@sha256:" + "a" * 64
    command = module.launch_command(image, socket_gid=999)
    assert command[-1] == image
    assert command[command.index("--env-file") + 1] == "/run/lunaris-sim/worker.env"
    assert "--read-only" in command
    assert command[command.index("--user") + 1] == "1000:1000"
    assert command[command.index("--group-add") + 1] == "999"
    assert "--privileged" not in command
    assert "--network=host" not in command
    assert command[command.index("--stop-timeout") + 1] == "300"


@pytest.mark.parametrize(
    "image",
    ["repo:latest", "repo@sha256:abc", "https://example/image", "repo@sha256:" + "a" * 64 + "\n"],
)
def test_bootstrap_refuses_unpinned_or_malformed_images(image):
    with pytest.raises(ValueError):
        _bootstrap().launch_command(image, socket_gid=999)


def test_prepare_retrieves_secrets_without_putting_them_in_process_arguments(monkeypatch, tmp_path):
    module = _bootstrap()
    monkeypatch.setenv("DOCKER_CONFIG", str(tmp_path / "docker-before"))
    monkeypatch.setattr(module, "_RUN", tmp_path / "run")
    monkeypatch.setattr(module, "_token", lambda *_: {"access_token": "imds-secret"})
    requests, commands = [], []

    def respond(request):
        requests.append(request)
        if request.full_url.endswith("/oauth2/exchange"):
            return {"refresh_token": "registry-secret"}
        if "/secrets/" in request.full_url:
            return {"value": "vault-secret"}
        return []

    monkeypatch.setattr(module, "_json", respond)
    monkeypatch.setattr(
        module.subprocess, "run", lambda command, **kw: commands.append((command, kw))
    )
    image = "example.azurecr.io/lunaris-sim-worker@sha256:" + "a" * 64
    module._prepare(
        module.SimConfiguration(
            **{
                "worker_image": image,
                "verifier_image": image,
                "vault_uri": "https://example.vault.azure.net/",
                "identity": "identity",
                "tenant": "tenant",
                "supabase_url": "https://example.supabase.co",
                "with_byok": True,
            }
        )
    )
    assert all("secret" not in str(command) for command, _ in commands)
    assert commands[0][1]["input"] == "registry-secret"
    env_file = tmp_path / "run/worker.env"
    assert env_file.stat().st_mode & 0o777 == 0o600
    assert "LUNARIS_KEY_ENC_MASTER=vault-secret" in env_file.read_text()
    assert any("/rest/v1/live_sim_requests?" in request.full_url for request in requests)


@pytest.mark.parametrize("sandbox_ready", [False, True])
def test_install_waits_for_real_sandbox_readiness_before_success(
    tmp_path, monkeypatch, sandbox_ready
):
    import os
    import subprocess

    from install import installation_script
    from sim_configuration import SimConfiguration

    commands = tmp_path / "bin"
    commands.mkdir()
    docker = commands / "docker"
    docker.write_text(
        '#!/bin/sh\nif [ "$1" = inspect ]; then echo true; exit 0; fi\n'
        + ("exit 0\n" if sandbox_ready else "exit 1\n")
    )
    docker.chmod(0o755)
    for name in ("cloud-init", "systemctl", "sleep"):
        executable = commands / name
        executable.write_text("#!/bin/sh\nexit 0\n")
        executable.chmod(0o755)
    config = SimConfiguration("worker", "verifier", "vault", "identity", "tenant", "supabase")
    script = installation_script(config)
    for directory in ("/opt/lunaris-sim", "/etc/lunaris-sim", "/etc/systemd/system"):
        target = tmp_path / directory.lstrip("/")
        target.mkdir(parents=True, exist_ok=True)
        script = script.replace(directory, str(target))
    monkeypatch.setenv("PATH", str(commands) + os.pathsep + os.environ["PATH"])
    result = subprocess.run(["bash"], input=script, text=True, capture_output=True, timeout=20)
    assert (result.returncode == 0) is sandbox_ready
    assert ("LUNARIS_SIM_SUPERVISOR_READY" in result.stdout) is sandbox_ready
    installed = tmp_path / "etc/lunaris-sim/config.json"
    assert installed.exists()
    assert installed.stat().st_mode & 0o777 == 0o600


def test_disabled_factory_stays_disabled_after_host_restart(tmp_path, monkeypatch):
    import re
    import subprocess

    import yaml

    workflow = yaml.safe_load((ROOT / ".github/workflows/cd-prod.yml").read_text())
    step = next(
        step
        for step in workflow["jobs"]["promote"]["steps"]
        if step.get("name") == "Stop simulator admissions when disabled"
    )
    script = re.search(r"--scripts '([^']+)'", step["run"]).group(1)
    commands = tmp_path / "bin"
    commands.mkdir()
    enabled = tmp_path / "enabled"
    enabled.touch()
    systemctl = commands / "systemctl"
    systemctl.write_text(
        '#!/bin/sh\ncase "$1" in\n'
        'disable) rm -f "$ENABLED_FILE";;\n'
        'is-enabled) test -f "$ENABLED_FILE";;\n'
        "is-active) exit 1;;\n"
        "stop) exit 0;;\nesac\n"
    )
    systemctl.chmod(0o755)
    monkeypatch.setenv("ENABLED_FILE", str(enabled))
    monkeypatch.setenv("PATH", str(commands) + ":/usr/bin:/bin")
    result = subprocess.run(["bash"], input=script, text=True, capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert "LUNARIS_SIM_SUPERVISOR_STOPPED" in result.stdout
    assert not enabled.exists(), "A reboot would restart the disabled factory"
