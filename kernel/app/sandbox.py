"""K4.1–K4.5 — Sandbox d'execució efímer per a eines de risc ≥2.

Cada invocació de risc ≥2 s'executa en un CONTENIDOR EFÍMER (`docker run --rm`,
destruït en acabar, K4.1) amb:
- seccomp restrictiu (K4.2) + `--cap-drop ALL` + `--security-opt no-new-privileges`.
- `--network none`: egress denegat pel namespace (K4.3); només loopback dins.
- cgroups v2: `--cpus 0.5 --memory 256m --pids-limit 32` + wall-clock 30s (K4.4).
- imatge sense shell (K4.5) → cap `sh`/`bash` per spawnejar.

NOTA INV-1: aquest mòdul és l'ÚNIC que usa `subprocess`, i NOMÉS per llançar
`docker` amb un argv FIX (shell=False). No executa codi arbitrari del xat al procés
del kernel: el payload corre AÏLLAT dins del contenidor blindat (aquest és el seu propòsit).
"""

from __future__ import annotations

import secrets
import subprocess  # llançament del sandbox (docker) amb argv FIX; shell desactivat
from dataclasses import dataclass

from .errors import SandboxError
from .risk import RiskLevel


@dataclass(frozen=True)
class SandboxSpec:
    image: str = "adeptify-sandbox:f2"
    seccomp_path: str = "/app/sandbox/seccomp.json"
    cpus: str = "0.5"
    memory: str = "256m"
    pids_limit: int = 32
    wall_clock_s: int = 30
    network: str = "none"


@dataclass(frozen=True)
class SandboxResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False
    oom_killed: bool = False


def requereix_sandbox(risk: RiskLevel | int) -> bool:
    """El sandbox és obligatori per a risc >= 2 (write-local o superior)."""
    return int(risk) >= int(RiskLevel.WRITE_LOCAL)


def build_docker_args(spec: SandboxSpec, *, name: str) -> list[str]:
    """argv FIX de `docker run` amb totes les restriccions (K4.1–K4.4). Pur i testejable."""
    return [
        "docker", "run", "--rm", "--name", name,
        "--network", spec.network,                       # K4.3 egress per namespace
        "--cap-drop", "ALL",                             # K4.2 capabilities mínimes
        "--security-opt", "no-new-privileges",
        "--security-opt", f"seccomp={spec.seccomp_path}",  # K4.2 seccomp
        "--read-only",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m",
        "--cpus", spec.cpus,                             # K4.4 CPU
        "--memory", spec.memory, "--memory-swap", spec.memory,  # K4.4 mem (sense swap → OOM)
        "--pids-limit", str(spec.pids_limit),            # K4.4 PIDs
        spec.image,
    ]


def run_sandboxed(payload_code: str, *, spec: SandboxSpec | None = None,
                  name: str | None = None) -> SandboxResult:
    """Executa `payload_code` (Python) DINS del sandbox blindat. Destrueix el
    contenidor en acabar (--rm) i imposa el wall-clock (K4.4)."""
    spec = spec or SandboxSpec()
    name = name or f"adsbx-{secrets.token_hex(4)}"
    args = [*build_docker_args(spec, name=name), "-c", payload_code]
    try:
        proc = subprocess.run(  # noqa: S603 - argv FIX, shell=False; veure docstring INV-1
            args, capture_output=True, text=True, timeout=spec.wall_clock_s, check=False,
        )
    except subprocess.TimeoutExpired:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, check=False)  # noqa: S603,S607
        return SandboxResult(124, "", f"wall-clock {spec.wall_clock_s}s superat", timed_out=True)
    except FileNotFoundError as exc:  # docker no disponible
        raise SandboxError("docker no disponible per al sandbox") from exc
    oom = proc.returncode == 137 or "OOMKilled" in (proc.stderr or "")
    return SandboxResult(proc.returncode, proc.stdout, proc.stderr, oom_killed=oom)
