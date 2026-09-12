"""Create a secret-free Azure Run Command script from reviewed repository files."""

import base64
import json
import os
import shlex
from dataclasses import asdict
from pathlib import Path

from sim_configuration import SimConfiguration

_ROOT = Path(__file__).resolve().parent


_READINESS = [
    "systemctl daemon-reload",
    "systemctl enable lunaris-sim.service",
    "systemctl restart lunaris-sim.service",
    # Startup includes private pulls and a real Docker/Chromium self-check. Reject a green
    # systemd status while the bootstrap is still downloading images or fetching secrets.
    "for attempt in $(seq 1 120); do",
    "  if docker inspect --format '{{.State.Running}}' lunaris-sim-supervisor "
    "2>/dev/null | grep -qx true; then",
    "    sleep 10",
    "    if docker exec lunaris-sim-supervisor test -f /tmp/lunaris-sim-ready; then",
    "    echo LUNARIS_SIM_SUPERVISOR_READY",
    "    exit 0",
    "    fi",
    "  fi",
    "  sleep 5",
    "done",
    "exit 1",
]


def installation_script(config: SimConfiguration) -> str:
    files = {
        "/opt/lunaris-sim/sim_configuration.py": (_ROOT / "sim_configuration.py").read_bytes(),
        "/opt/lunaris-sim/bootstrap.py": (_ROOT / "bootstrap.py").read_bytes(),
        "/etc/systemd/system/lunaris-sim.service": (_ROOT / "lunaris-sim.service").read_bytes(),
        "/etc/lunaris-sim/config.json": json.dumps(asdict(config)).encode(),
    }
    commands = [
        "set -eu",
        "cloud-init status --wait",
        "umask 077",
        "mkdir -p /opt/lunaris-sim /etc/lunaris-sim",
    ]
    for path, data in files.items():
        commands.append(
            "printf %s "
            + shlex.quote(base64.b64encode(data).decode())
            + " | base64 -d > "
            + shlex.quote(path)
        )
    commands.extend(_READINESS)
    return "\n".join(commands) + "\n"


if __name__ == "__main__":
    configuration = SimConfiguration(
        **{
            "worker_image": os.environ["SIM_WORKER_IMAGE"],
            "verifier_image": os.environ["SIM_VERIFIER_IMAGE"],
            "vault_uri": os.environ["SIM_VAULT_URI"],
            "identity": os.environ["SIM_IDENTITY"],
            "tenant": os.environ["SIM_TENANT"],
            "supabase_url": os.environ["SIM_SUPABASE_URL"],
            "with_byok": os.environ.get("SIM_WITH_BYOK") == "true",
        }
    )
    Path(os.environ["SIM_INSTALL_SCRIPT"]).write_text(installation_script(configuration))
