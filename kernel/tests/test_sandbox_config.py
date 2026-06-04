"""K4.1–K4.4 — configuració del sandbox (flags de docker). Test pur (sense docker)."""

from __future__ import annotations

from app.risk import RiskLevel
from app.sandbox import SandboxSpec, build_docker_args, requereix_sandbox


def test_requereix_sandbox_per_risc_2():
    assert requereix_sandbox(RiskLevel.INFO) is False
    assert requereix_sandbox(RiskLevel.READ) is False
    assert requereix_sandbox(RiskLevel.WRITE_LOCAL) is True       # risc >= 2 → sandbox
    assert requereix_sandbox(RiskLevel.WRITE_EXTERNAL) is True
    assert requereix_sandbox(RiskLevel.IRREVERSIBLE) is True


def test_build_docker_args_totes_les_restriccions():
    s = " ".join(build_docker_args(SandboxSpec(), name="t1"))
    assert "--rm" in s                          # K4.1 efímer (destruït en acabar)
    assert "--network none" in s                # K4.3 egress per namespace
    assert "--cap-drop ALL" in s                # K4.2 capabilities mínimes
    assert "no-new-privileges" in s
    assert "seccomp=" in s                       # K4.2 perfil seccomp
    assert "--read-only" in s
    assert "--cpus 0.5" in s                     # K4.4 CPU
    assert "--memory 256m" in s                  # K4.4 mem
    assert "--pids-limit 32" in s               # K4.4 PIDs


def test_sense_swap_per_garantir_oom():
    args = build_docker_args(SandboxSpec(memory="256m"), name="t")
    i, j = args.index("--memory"), args.index("--memory-swap")
    assert args[i + 1] == args[j + 1] == "256m"  # mem == mem-swap → OOM real al límit


def test_imatge_al_final_abans_del_payload():
    args = build_docker_args(SandboxSpec(), name="t")
    assert args[-1] == SandboxSpec().image  # el payload (`-c …`) s'afegeix després
