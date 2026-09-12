"""Root-owned VM bootstrap. Secrets use IMDS/Key Vault and never command arguments."""

import json
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from sim_configuration import SimConfiguration

_RUN = Path("/run/lunaris-sim")
_PIN = re.compile(r"[a-z0-9.-]+\.azurecr\.io/[a-z0-9/-]+@sha256:[a-f0-9]{64}")


def launch_command(image: str, *, socket_gid: int) -> list[str]:
    """The Docker socket belongs exclusively to the trusted supervisor."""
    if not _PIN.fullmatch(image):
        raise ValueError("A digest-pinned ACR image is required")
    return [
        "docker",
        "run",
        "--rm",
        "--name",
        "lunaris-sim-supervisor",
        "--user",
        "1000:1000",
        "--group-add",
        str(socket_gid),
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,size=256m",
        "--stop-timeout",
        "300",
        "--memory",
        "1g",
        "--pids-limit",
        "128",
        "--log-opt",
        "max-size=10m",
        "--log-opt",
        "max-file=3",
        "--mount",
        "type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock",
        "--env-file",
        str(_RUN / "worker.env"),
        image,
    ]


def _json(request: Request) -> dict:
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def _token(resource: str, identity: str) -> dict:
    query = urlencode({"api-version": "2018-02-01", "resource": resource, "msi_res_id": identity})
    return _json(
        Request(
            "http://169.254.169.254/metadata/identity/oauth2/token?" + query,
            headers={"Metadata": "true"},
        )
    )


def _validate(config: SimConfiguration) -> tuple[str, str]:
    for image in (config.worker_image, config.verifier_image):
        if not _PIN.fullmatch(image):
            raise ValueError("Unpinned image")
    registry = config.worker_image.split("/", 1)[0]
    if config.verifier_image.split("/", 1)[0] != registry:
        raise ValueError("Images must use the same registry")
    vault = config.vault_uri.rstrip("/")
    if not re.fullmatch(r"https://[a-zA-Z0-9-]+\.vault\.azure\.net", vault):
        raise ValueError("Invalid vault host")
    if not re.fullmatch(r"https://[a-zA-Z0-9-]+\.supabase\.co", config.supabase_url.rstrip("/")):
        raise ValueError("Invalid Supabase host")
    return registry, vault


def _pull_images(config: SimConfiguration, registry: str) -> None:
    os.environ["DOCKER_CONFIG"] = str(_RUN / "docker")
    arm = _token("https://management.azure.com/", config.identity)
    exchange = _json(
        Request(
            "https://" + registry + "/oauth2/exchange",
            data=urlencode(
                {
                    "grant_type": "access_token",
                    "service": registry,
                    "tenant": config.tenant,
                    "access_token": arm["access_token"],
                }
            ).encode(),
        )
    )
    subprocess.run(
        [
            "docker",
            "login",
            registry,
            "--username",
            "00000000-0000-0000-0000-000000000000",
            "--password-stdin",
        ],
        input=exchange["refresh_token"],
        text=True,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    for image in (config.worker_image, config.verifier_image):
        subprocess.run(["docker", "pull", image], check=True)


def _environment(config: SimConfiguration, vault: str) -> dict[str, str]:
    token = _token("https://vault.azure.net", config.identity)["access_token"]
    environment = {
        "SUPABASE_URL": config.supabase_url,
        "LUNARIS_PIPELINE": "agent",
        "LUNARIS_SIM_VERIFIER_IMAGE": config.verifier_image,
        "LUNARIS_SIM_SECCOMP_PATH": "/etc/lunaris/sim-seccomp.json",
    }
    secrets = {
        "SUPABASE_SERVICE_ROLE_KEY": "supabase-service-role-key",
        "ANTHROPIC_API_KEY": "anthropic-api-key",
    }
    if config.with_byok:
        secrets["LUNARIS_KEY_ENC_MASTER"] = "lunaris-key-enc-master"
    for name, secret in secrets.items():
        environment[name] = _json(
            Request(
                vault + "/secrets/" + secret + "?api-version=7.4",
                headers={"Authorization": "Bearer " + token},
            )
        )["value"]
    return environment


def _check_database(environment: dict[str, str]) -> None:
    key = environment["SUPABASE_SERVICE_ROLE_KEY"]
    _json(
        Request(
            environment["SUPABASE_URL"].rstrip("/")
            + "/rest/v1/live_sim_requests?select=cache_key&limit=1",
            headers={"apikey": key, "Authorization": "Bearer " + key},
        )
    )


def _write_environment(environment: dict[str, str]) -> None:
    if any("\n" in value or "\r" in value for value in environment.values()):
        raise ValueError("Environment values must be single-line")
    descriptor = os.open(_RUN / "worker.env", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        handle.write("".join(f"{name}={value}\n" for name, value in environment.items()))


def _prepare(config: SimConfiguration) -> None:
    registry, vault = _validate(config)
    _RUN.mkdir(mode=0o700, parents=True, exist_ok=True)
    _pull_images(config, registry)
    environment = _environment(config, vault)
    _check_database(environment)
    _write_environment(environment)


def _main() -> None:
    os.umask(0o077)
    config = SimConfiguration(**json.loads(Path("/etc/lunaris-sim/config.json").read_text()))
    _prepare(config)
    command = launch_command(
        config.worker_image, socket_gid=Path("/var/run/docker.sock").stat().st_gid
    )
    os.execvp(command[0], command)


if __name__ == "__main__":
    try:
        _main()
    except Exception as error:
        # Provider/HTTP exceptions can contain credentials; report only the exception type.
        raise SystemExit("Simulator supervisor startup failed: " + type(error).__name__) from None
