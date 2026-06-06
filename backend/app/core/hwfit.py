"""Dimensionament local de models LLM segons maquinari disponible.

El modul no descarrega pesos, no arrenca serveis i no fa shell-out. Nomes genera
un informe reproduible per decidir quin model auto-allotjat encaixa en una GPU.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import shutil
from dataclasses import asdict, dataclass, field
from typing import Any


CATALOG_VERSION = "2026-06-06.1"
CATALOG_SCHEMA = "adeptify.hwfit.catalog.v1"
DEFAULT_RAG_VRAM_RESERVE_GB = 1.5


@dataclass(frozen=True)
class HardwareProfile:
    """Perfil de maquinari detectat o injectat per a una simulacio."""

    gpu_name: str | None = None
    gpu_count: int = 0
    vram_gb: float = 0.0
    ram_gb: float = 0.0
    disk_free_gb: float | None = None
    cuda_available: bool = False
    detected_by: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    @property
    def vram_total_gb(self) -> float:
        return max(0.0, self.vram_gb) * max(1, self.gpu_count or 1)


@dataclass(frozen=True)
class ModelCatalogEntry:
    """Entrada curada del cataleg de models permesos per Adeptify."""

    id: str
    nom: str
    provider_id: str
    rol: str
    backend: str
    quantitzacio: str
    context_tokens: int
    min_vram_gb: float
    recom_vram_gb: float
    min_ram_gb: float
    recom_ram_gb: float
    min_disk_gb: float
    gpu_obligatoria: bool = False
    permet_cpu_offload: bool = True
    llicencia: str = ""
    requereix_aprovacio: bool = True
    notes: tuple[str, ...] = ()
    prioritat: int = 50


@dataclass(frozen=True)
class ModelFit:
    """Resultat de scoring d'un model concret sobre un perfil de maquinari."""

    model_id: str
    nom: str
    rol: str
    backend: str
    quantitzacio: str
    compatible: bool
    estat: str
    puntuacio: int
    motius: tuple[str, ...] = ()
    avisos: tuple[str, ...] = ()
    requisits: dict[str, float | bool | str] = field(default_factory=dict)
    accio_humana: str = "Aprovar llicencia/descarrega i verificar manifest abans de servir."


MODEL_CATALOG: tuple[ModelCatalogEntry, ...] = (
    ModelCatalogEntry(
        id="qwen2_5_7b_ollama_q4",
        nom="Qwen2.5 7B Instruct",
        provider_id="qwen2.5:7b",
        rol="interactiu",
        backend="ollama",
        quantitzacio="GGUF/Q4",
        context_tokens=32768,
        min_vram_gb=6.0,
        recom_vram_gb=8.0,
        min_ram_gb=12.0,
        recom_ram_gb=24.0,
        min_disk_gb=5.0,
        gpu_obligatoria=False,
        permet_cpu_offload=True,
        llicencia="Apache-2.0",
        notes=(
            "Model interactiu recomanat en el PC actual amb 8 GB VRAM.",
            "Mantingut per latencia i tool-calling estable.",
        ),
        prioritat=95,
    ),
    ModelCatalogEntry(
        id="aya_8b_ollama_q4",
        nom="Aya 8B",
        provider_id="aya:8b",
        rol="catala_dev",
        backend="ollama",
        quantitzacio="GGUF/Q4",
        context_tokens=8192,
        min_vram_gb=6.0,
        recom_vram_gb=8.0,
        min_ram_gb=12.0,
        recom_ram_gb=24.0,
        min_disk_gb=5.0,
        gpu_obligatoria=False,
        permet_cpu_offload=True,
        llicencia="oberta",
        notes=("Alternativa de desenvolupament per catala aproximat.",),
        prioritat=60,
    ),
    ModelCatalogEntry(
        id="gemma3_12b_skills_ollama_q4",
        nom="Gemma 3 12B",
        provider_id="gemma3:12b",
        rol="skills_catala",
        backend="ollama",
        quantitzacio="GGUF/Q4",
        context_tokens=8192,
        min_vram_gb=10.0,
        recom_vram_gb=16.0,
        min_ram_gb=18.0,
        recom_ram_gb=32.0,
        min_disk_gb=9.0,
        gpu_obligatoria=False,
        permet_cpu_offload=True,
        llicencia="Gemma Terms",
        notes=("Qualitat linguistica alta; adequat per skills no urgents.",),
        prioritat=72,
    ),
    ModelCatalogEntry(
        id="qwen3_coder_30b_rag_ollama_q4_ctx8k",
        nom="Qwen3 Coder 30B RAG ctx 8k",
        provider_id="qwen3-coder-rag",
        rol="batch",
        backend="ollama",
        quantitzacio="GGUF/Q4 + ctx 8192",
        context_tokens=8192,
        min_vram_gb=20.0,
        recom_vram_gb=24.0,
        min_ram_gb=28.0,
        recom_ram_gb=64.0,
        min_disk_gb=20.0,
        gpu_obligatoria=False,
        permet_cpu_offload=True,
        llicencia="Apache-2.0",
        notes=(
            "Validat nomes com a model batch/no interactiu en 8 GB VRAM + 31 GB RAM.",
            "A 32k context no carrega en el PC actual.",
        ),
        prioritat=58,
    ),
    ModelCatalogEntry(
        id="gemma4_12b_full_unified",
        nom="Gemma 4 12B multimodal",
        provider_id="google/gemma-4-12b",
        rol="multimodal_local",
        backend="transformers/litert-lm",
        quantitzacio="BF16/full precision",
        context_tokens=256000,
        min_vram_gb=16.0,
        recom_vram_gb=20.0,
        min_ram_gb=24.0,
        recom_ram_gb=48.0,
        min_disk_gb=25.0,
        gpu_obligatoria=True,
        permet_cpu_offload=False,
        llicencia="Apache-2.0",
        notes=(
            "Anunciat per Google el 2026-06-03; requereix 16 GB de VRAM o memoria unificada.",
            "No recomanat per al portatil actual de 8 GB VRAM.",
        ),
        prioritat=74,
    ),
    ModelCatalogEntry(
        id="gemma4_12b_qat_q4_candidate",
        nom="Gemma 4 12B QAT Q4_0",
        provider_id="google/gemma-4-12b-it-qat-q4_0-gguf",
        rol="multimodal_candidate",
        backend="llama.cpp/ollama",
        quantitzacio="QAT Q4_0 GGUF",
        context_tokens=256000,
        min_vram_gb=8.0,
        recom_vram_gb=12.0,
        min_ram_gb=24.0,
        recom_ram_gb=48.0,
        min_disk_gb=10.0,
        gpu_obligatoria=False,
        permet_cpu_offload=True,
        llicencia="Apache-2.0",
        notes=(
            "Checkpoint QAT/Q4_0 publicat per Google per reduir memoria.",
            "Candidat a PoC local; no substituir el model interactiu sense benchmark.",
        ),
        prioritat=62,
    ),
    ModelCatalogEntry(
        id="salamandra_7b_vllm_fp16",
        nom="BSC Salamandra 7B Instruct",
        provider_id="BSC-LT/salamandra-7b-instruct",
        rol="catala_gpu",
        backend="vllm",
        quantitzacio="FP16",
        context_tokens=8192,
        min_vram_gb=9.0,
        recom_vram_gb=12.0,
        min_ram_gb=16.0,
        recom_ram_gb=32.0,
        min_disk_gb=15.0,
        gpu_obligatoria=True,
        permet_cpu_offload=False,
        llicencia="CC-BY-SA",
        notes=("Model catala per GPU dedicada; vLLM necessita marge de VRAM.",),
        prioritat=70,
    ),
    ModelCatalogEntry(
        id="llama_3_3_70b_awq_vllm",
        nom="Llama 3.3 70B Instruct AWQ",
        provider_id="hugging-quants/Llama-3.3-70B-Instruct-AWQ-INT4",
        rol="produccio_gpu",
        backend="vllm",
        quantitzacio="AWQ 4-bit",
        context_tokens=32768,
        min_vram_gb=42.0,
        recom_vram_gb=48.0,
        min_ram_gb=32.0,
        recom_ram_gb=64.0,
        min_disk_gb=45.0,
        gpu_obligatoria=True,
        permet_cpu_offload=False,
        llicencia="Meta Llama 3.3",
        notes=("Perfil pilot A100 80 GB o equivalent.",),
        prioritat=88,
    ),
    ModelCatalogEntry(
        id="qwen2_5_72b_awq_vllm",
        nom="Qwen2.5 72B Instruct AWQ",
        provider_id="Qwen/Qwen2.5-72B-Instruct-AWQ",
        rol="produccio_gpu",
        backend="vllm",
        quantitzacio="AWQ 4-bit",
        context_tokens=32768,
        min_vram_gb=40.0,
        recom_vram_gb=48.0,
        min_ram_gb=32.0,
        recom_ram_gb=64.0,
        min_disk_gb=45.0,
        gpu_obligatoria=True,
        permet_cpu_offload=False,
        llicencia="Apache-2.0",
        notes=("Alternativa pilot A100 80 GB; bona per multilingue.",),
        prioritat=90,
    ),
)


def _asdict_sense_tuples(obj: Any) -> dict[str, Any]:
    data = asdict(obj)
    for k, v in list(data.items()):
        if isinstance(v, tuple):
            data[k] = list(v)
    return data


def catalog_manifest() -> dict[str, Any]:
    """Manifest canonic del cataleg curat, per verificar integritat."""

    return {
        "schema": CATALOG_SCHEMA,
        "version": CATALOG_VERSION,
        "models": [_asdict_sense_tuples(m) for m in MODEL_CATALOG],
    }


def catalog_sha256() -> str:
    raw = json.dumps(
        catalog_manifest(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def catalog_signature() -> str:
    return f"sha256:{catalog_sha256()}"


def _env_float(*names: str) -> float | None:
    for name in names:
        val = os.getenv(name)
        if val is None or str(val).strip() == "":
            continue
        try:
            return float(str(val).replace(",", "."))
        except ValueError:
            return None
    return None


def _env_int(*names: str) -> int | None:
    val = _env_float(*names)
    return int(val) if val is not None else None


def _system_ram_gb() -> tuple[float, str] | tuple[None, str]:
    try:
        import psutil  # type: ignore

        return psutil.virtual_memory().total / (1024**3), "psutil"
    except Exception:
        pass

    if os.name == "nt":
        try:
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            mem = MEMORYSTATUSEX()
            mem.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem)):
                return mem.ullTotalPhys / (1024**3), "ctypes"
        except Exception:
            pass

    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        return (pages * page_size) / (1024**3), "sysconf"
    except Exception:
        return None, "desconegut"


def _torch_gpu() -> tuple[str | None, int, float, bool, str] | None:
    try:
        import torch  # type: ignore

        if not torch.cuda.is_available():
            return None, 0, 0.0, False, "torch"
        count = int(torch.cuda.device_count() or 1)
        total = 0.0
        names: list[str] = []
        for idx in range(count):
            props = torch.cuda.get_device_properties(idx)
            total += float(props.total_memory) / (1024**3)
            names.append(str(props.name))
        name = " + ".join(names) if names else None
        per_gpu = total / max(count, 1)
        return name, count, per_gpu, True, "torch.cuda"
    except Exception:
        return None


def detecta_hardware(path_disc: str | None = None) -> HardwareProfile:
    """Detecta maquinari local sense executar comandes externes.

    Overrides admesos per fer informes reproduibles:
    ADEPTIFY_GPU_NAME, ADEPTIFY_GPU_COUNT, ADEPTIFY_VRAM_GB, ADEPTIFY_RAM_GB,
    ADEPTIFY_DISK_FREE_GB.
    """

    detected_by: list[str] = []
    notes: list[str] = []

    gpu_name = os.getenv("ADEPTIFY_GPU_NAME") or os.getenv("GPU_NAME")
    gpu_count = _env_int("ADEPTIFY_GPU_COUNT", "GPU_COUNT")
    vram_gb = _env_float("ADEPTIFY_VRAM_GB", "VRAM_GB")
    cuda_available = False

    torch_info = _torch_gpu()
    if torch_info is not None:
        t_name, t_count, t_vram, t_cuda, source = torch_info
        detected_by.append(source)
        if gpu_name is None:
            gpu_name = t_name
        if gpu_count is None:
            gpu_count = t_count
        if vram_gb is None:
            vram_gb = t_vram
        cuda_available = t_cuda

    if gpu_name or gpu_count is not None or vram_gb is not None:
        detected_by.append("env" if os.getenv("ADEPTIFY_VRAM_GB") else "hardware")

    ram_gb = _env_float("ADEPTIFY_RAM_GB", "RAM_GB")
    if ram_gb is None:
        ram_detectada, source = _system_ram_gb()
        if ram_detectada is not None:
            ram_gb = ram_detectada
            detected_by.append(f"ram:{source}")
    else:
        detected_by.append("ram:env")

    disk_free_gb = _env_float("ADEPTIFY_DISK_FREE_GB", "DISK_FREE_GB")
    if disk_free_gb is None:
        try:
            usage = shutil.disk_usage(path_disc or os.getcwd())
            disk_free_gb = usage.free / (1024**3)
            detected_by.append("disc:shutil")
        except Exception:
            disk_free_gb = None
            notes.append("No s'ha pogut detectar l'espai lliure en disc.")
    else:
        detected_by.append("disc:env")

    gpu_count = max(0, int(gpu_count or 0))
    vram_gb = round(float(vram_gb or 0.0), 2)
    ram_gb = round(float(ram_gb or 0.0), 2)
    if disk_free_gb is not None:
        disk_free_gb = round(float(disk_free_gb), 2)

    if gpu_count == 0 or vram_gb <= 0:
        notes.append("No s'ha detectat GPU CUDA dedicada; els models GPU-only no encaixen.")
        cuda_available = False

    return HardwareProfile(
        gpu_name=gpu_name,
        gpu_count=gpu_count,
        vram_gb=vram_gb,
        ram_gb=ram_gb,
        disk_free_gb=disk_free_gb,
        cuda_available=cuda_available,
        detected_by=tuple(dict.fromkeys(detected_by)),
        notes=tuple(notes),
    )


def _marge(valor: float | None, minim: float) -> float | None:
    if valor is None:
        return None
    return round(valor - minim, 2)


def avalua_model(
    model: ModelCatalogEntry,
    hardware: HardwareProfile,
    *,
    reserva_vram_gb: float = DEFAULT_RAG_VRAM_RESERVE_GB,
) -> ModelFit:
    """Calcula si un model encaixa i en quin estat operatiu quedaria."""

    vram_llm = max(0.0, hardware.vram_total_gb - reserva_vram_gb)
    ram_gb = hardware.ram_gb
    disk_free_gb = hardware.disk_free_gb

    ram_ok = ram_gb >= model.min_ram_gb
    disk_ok = disk_free_gb is None or disk_free_gb >= model.min_disk_gb
    vram_ok = vram_llm >= model.min_vram_gb
    gpu_ok = hardware.cuda_available and vram_ok

    if model.gpu_obligatoria:
        compatible = bool(gpu_ok and ram_ok and disk_ok)
    else:
        compatible = bool(ram_ok and disk_ok)

    motius: list[str] = []
    avisos: list[str] = []
    puntuacio = model.prioritat

    if ram_ok:
        motius.append(f"RAM suficient ({ram_gb:.1f} GB >= {model.min_ram_gb:.1f} GB).")
        if _marge(ram_gb, model.min_ram_gb) is not None and ram_gb - model.min_ram_gb < 4:
            avisos.append("RAM al limit; no recomanat per concurrencia.")
            puntuacio -= 12
    else:
        motius.append(f"RAM insuficient ({ram_gb:.1f} GB < {model.min_ram_gb:.1f} GB).")
        puntuacio -= 35

    if disk_ok:
        if disk_free_gb is not None:
            motius.append(
                f"Disc suficient ({disk_free_gb:.1f} GB lliures >= {model.min_disk_gb:.1f} GB)."
            )
    else:
        motius.append(
            f"Disc insuficient ({disk_free_gb:.1f} GB lliures < {model.min_disk_gb:.1f} GB)."
        )
        puntuacio -= 20

    if model.min_vram_gb <= 0:
        motius.append("No requereix VRAM dedicada.")
    elif gpu_ok:
        motius.append(
            f"VRAM util per LLM suficient ({vram_llm:.1f} GB >= {model.min_vram_gb:.1f} GB)."
        )
        if vram_llm >= model.recom_vram_gb:
            puntuacio += 8
    elif model.gpu_obligatoria:
        motius.append(
            f"VRAM insuficient per GPU-only ({vram_llm:.1f} GB < {model.min_vram_gb:.1f} GB)."
        )
        puntuacio -= 45
    elif hardware.cuda_available and hardware.vram_total_gb > 0:
        motius.append(
            f"Pot funcionar amb offload CPU/RAM; VRAM recomanada no assolida ({vram_llm:.1f} GB < {model.min_vram_gb:.1f} GB)."
        )
        avisos.append("Mode degradat: part del model anira a CPU/RAM.")
        puntuacio -= 14
    else:
        motius.append("Sense GPU CUDA; nomes mode CPU/RAM si el backend ho permet.")
        avisos.append("Latencia alta esperable sense GPU CUDA.")
        puntuacio -= 18

    if model.rol == "batch" and compatible:
        avisos.append("Apte nomes per tasques batch/no interactives.")
    if "candidate" in model.rol and compatible:
        avisos.append("Candidat experimental: cal benchmark local abans de produccio.")
    if "multimodal" in model.rol and compatible:
        avisos.append("El flux multimodal encara no esta integrat al producte.")
    if model.backend == "vllm" and compatible:
        avisos.append("Arrencar vLLM requereix aprovacio humana i verificacio del manifest.")

    if compatible and not avisos:
        estat = "recomanat"
    elif compatible:
        estat = "compatible_amb_avisos"
    else:
        estat = "no_compatible"

    return ModelFit(
        model_id=model.id,
        nom=model.nom,
        rol=model.rol,
        backend=model.backend,
        quantitzacio=model.quantitzacio,
        compatible=compatible,
        estat=estat,
        puntuacio=max(0, min(100, int(puntuacio))),
        motius=tuple(motius),
        avisos=tuple(avisos),
        requisits={
            "min_vram_gb": model.min_vram_gb,
            "recom_vram_gb": model.recom_vram_gb,
            "min_ram_gb": model.min_ram_gb,
            "recom_ram_gb": model.recom_ram_gb,
            "min_disk_gb": model.min_disk_gb,
            "gpu_obligatoria": model.gpu_obligatoria,
            "reserva_vram_rag_gb": reserva_vram_gb,
        },
    )


def avalua_cataleg(
    hardware: HardwareProfile,
    *,
    reserva_vram_gb: float = DEFAULT_RAG_VRAM_RESERVE_GB,
) -> list[ModelFit]:
    resultats = [
        avalua_model(model, hardware, reserva_vram_gb=reserva_vram_gb)
        for model in MODEL_CATALOG
    ]
    return sorted(
        resultats,
        key=lambda r: (r.compatible, r.puntuacio, r.model_id),
        reverse=True,
    )


def _primer(resultats: list[ModelFit], rol: str) -> ModelFit | None:
    for r in resultats:
        if r.compatible and r.rol == rol:
            return r
    return None


def informe_hwfit(
    hardware: HardwareProfile | None = None,
    *,
    reserva_vram_gb: float = DEFAULT_RAG_VRAM_RESERVE_GB,
) -> dict[str, Any]:
    """Informe complet per API/CLI. No te efectes laterals."""

    hw = hardware or detecta_hardware()
    resultats = avalua_cataleg(hw, reserva_vram_gb=reserva_vram_gb)
    interactiu = _primer(resultats, "interactiu")
    batch = _primer(resultats, "batch")
    produccio_gpu = _primer(resultats, "produccio_gpu")

    return {
        "maquinari": _asdict_sense_tuples(hw),
        "cataleg": {
            "schema": CATALOG_SCHEMA,
            "versio": CATALOG_VERSION,
            "sha256": catalog_sha256(),
            "signatura": catalog_signature(),
            "models": len(MODEL_CATALOG),
            "allowlist": [m.id for m in MODEL_CATALOG],
        },
        "politica": {
            "descarrega_automatica": False,
            "servei_automatic": False,
            "requereix_aprovacio_humana": True,
            "reserva_vram_rag_gb": reserva_vram_gb,
        },
        "recomanacio": {
            "interactiu": interactiu.model_id if interactiu else None,
            "batch": batch.model_id if batch else None,
            "produccio_gpu": produccio_gpu.model_id if produccio_gpu else None,
        },
        "resultats": [_asdict_sense_tuples(r) for r in resultats],
    }
