"""CLI: informa quin model local encaixa en el maquinari disponible.

Us:
    python -m scripts.hwfit_report
    python -m scripts.hwfit_report --json
    python -m scripts.hwfit_report --gpu-name "RTX 5070 Laptop" --vram-gb 8 --ram-gb 31

No descarrega models, no arrenca vLLM/Ollama i no fa cap crida de xarxa.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.hwfit import HardwareProfile, detecta_hardware, informe_hwfit  # noqa: E402


def _hardware_des_args(args: argparse.Namespace) -> HardwareProfile | None:
    if (
        args.gpu_name is None
        and args.vram_gb is None
        and args.ram_gb is None
        and args.disk_free_gb is None
    ):
        return None
    detectat = detecta_hardware()
    gpu_count = args.gpu_count if args.gpu_count is not None else detectat.gpu_count
    if gpu_count == 0 and args.vram_gb is not None:
        gpu_count = 1
    return HardwareProfile(
        gpu_name=args.gpu_name or detectat.gpu_name,
        gpu_count=gpu_count,
        vram_gb=args.vram_gb if args.vram_gb is not None else detectat.vram_gb,
        ram_gb=args.ram_gb if args.ram_gb is not None else detectat.ram_gb,
        disk_free_gb=args.disk_free_gb if args.disk_free_gb is not None else detectat.disk_free_gb,
        cuda_available=bool(gpu_count and (args.vram_gb or detectat.vram_gb)),
        detected_by=("cli",),
        notes=("Perfil simulat via arguments CLI.",),
    )


def _text(report: dict) -> str:
    hw = report["maquinari"]
    rec = report["recomanacio"]
    lines = [
        "Adeptify hwfit",
        f"GPU: {hw.get('gpu_name') or 'no detectada'} x{hw.get('gpu_count')} · VRAM {hw.get('vram_gb')} GB",
        f"RAM: {hw.get('ram_gb')} GB · Disc lliure: {hw.get('disk_free_gb')} GB",
        f"Cataleg: {report['cataleg']['versio']} · {report['cataleg']['signatura']}",
        f"Recomanat interactiu: {rec.get('interactiu') or '-'}",
        f"Recomanat batch: {rec.get('batch') or '-'}",
        f"Recomanat produccio GPU: {rec.get('produccio_gpu') or '-'}",
        "",
        "Models:",
    ]
    for r in report["resultats"]:
        marca = "OK" if r["compatible"] else "--"
        avis = f" · avisos: {len(r['avisos'])}" if r["avisos"] else ""
        lines.append(
            f"- {marca} {r['model_id']} ({r['backend']}, {r['rol']}): {r['estat']} · score {r['puntuacio']}{avis}"
        )
    lines.append("")
    lines.append("Accio: aprovar llicencia/descarrega i verificar manifest abans de servir cap model.")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Dimensionament local de models Adeptify.")
    ap.add_argument("--json", action="store_true", help="Sortida en JSON.")
    ap.add_argument("--gpu-name", help="Nom de GPU per a simulacio.")
    ap.add_argument("--gpu-count", type=int, help="Nombre de GPU per a simulacio.")
    ap.add_argument("--vram-gb", type=float, help="VRAM per GPU en GB.")
    ap.add_argument("--ram-gb", type=float, help="RAM total en GB.")
    ap.add_argument("--disk-free-gb", type=float, help="Disc lliure en GB.")
    args = ap.parse_args()

    report = informe_hwfit(_hardware_des_args(args))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
