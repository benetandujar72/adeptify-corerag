"""Tests del dimensionament de models locals (Sub-A Odysseus/K5)."""

from __future__ import annotations


def _per_id(report: dict) -> dict[str, dict]:
    return {r["model_id"]: r for r in report["resultats"]}


def test_hwfit_pc_actual_recomana_7b_i_deixa_30b_com_batch():
    from app.core.hwfit import HardwareProfile, informe_hwfit

    hw = HardwareProfile(
        gpu_name="NVIDIA GeForce RTX 5070 Laptop GPU",
        gpu_count=1,
        vram_gb=8.0,
        ram_gb=31.0,
        disk_free_gb=120.0,
        cuda_available=True,
        detected_by=("test",),
    )
    report = informe_hwfit(hw)
    resultats = _per_id(report)

    assert report["recomanacio"]["interactiu"] == "qwen2_5_7b_ollama_q4"
    assert resultats["qwen2_5_7b_ollama_q4"]["compatible"] is True
    assert resultats["qwen3_coder_30b_rag_ollama_q4_ctx8k"]["compatible"] is True
    assert resultats["qwen3_coder_30b_rag_ollama_q4_ctx8k"]["rol"] == "batch"
    assert resultats["gemma4_12b_full_unified"]["compatible"] is False
    assert resultats["gemma4_12b_qat_q4_candidate"]["compatible"] is True
    assert resultats["gemma4_12b_qat_q4_candidate"]["rol"] == "multimodal_candidate"
    assert resultats["gemma4_12b_qat_q4_candidate"]["avisos"]
    assert resultats["salamandra_7b_vllm_fp16"]["compatible"] is False
    assert resultats["llama_3_3_70b_awq_vllm"]["compatible"] is False


def test_hwfit_a100_permet_models_70b_awq_vllm():
    from app.core.hwfit import HardwareProfile, informe_hwfit

    hw = HardwareProfile(
        gpu_name="NVIDIA A100 80GB",
        gpu_count=1,
        vram_gb=80.0,
        ram_gb=128.0,
        disk_free_gb=500.0,
        cuda_available=True,
        detected_by=("test",),
    )
    resultats = _per_id(informe_hwfit(hw))

    assert resultats["llama_3_3_70b_awq_vllm"]["compatible"] is True
    assert resultats["qwen2_5_72b_awq_vllm"]["compatible"] is True
    assert resultats["gemma4_12b_full_unified"]["compatible"] is True
    assert resultats["salamandra_7b_vllm_fp16"]["compatible"] is True


def test_hwfit_cataleg_te_empremta_i_no_auto_descarrega():
    from app.core.hwfit import catalog_sha256, informe_hwfit

    report = informe_hwfit()
    assert len(catalog_sha256()) == 64
    assert report["cataleg"]["signatura"].startswith("sha256:")
    assert report["politica"]["descarrega_automatica"] is False
    assert report["politica"]["servei_automatic"] is False
    assert report["politica"]["requereix_aprovacio_humana"] is True


def _seed_usuaris(db):
    from app.core import users
    from app.db.models import Institucio

    db.add(Institucio(slug="inst_hw", nom="Centre HW", actiu=True))
    db.commit()
    users.crea_usuari(db, "dir_hw", "k", "direccio", institucio_id="inst_hw")
    users.crea_usuari(db, "doc_hw", "k", "docent", institucio_id="inst_hw")
    db.commit()


def _login(client, usuari: str) -> str:
    resp = client.post(
        "/api/auth/login",
        json={"usuari": usuari, "contrasenya": "k", "institucio": "inst_hw"},
    )
    assert resp.status_code == 200
    return resp.json()["token"]


def test_endpoint_hwfit_limitat_a_gestors(client, db):
    _seed_usuaris(db)
    token_doc = _login(client, "doc_hw")
    token_dir = _login(client, "dir_hw")

    r_doc = client.get(
        "/api/system/hardware-fit",
        headers={"Authorization": f"Bearer {token_doc}"},
    )
    assert r_doc.status_code == 403

    r_dir = client.get(
        "/api/system/hardware-fit",
        headers={"Authorization": f"Bearer {token_dir}"},
    )
    assert r_dir.status_code == 200
    body = r_dir.json()
    assert {"maquinari", "cataleg", "politica", "recomanacio", "resultats"} <= set(body)
    assert body["politica"]["descarrega_automatica"] is False
