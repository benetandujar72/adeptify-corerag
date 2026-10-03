"""Strict scanner guards use generated, disposable credentials only."""
from pathlib import Path
import json
import subprocess
from scripts import audita_secrets_repo as scanner
import pytest

def test_credencial_forta_no_es_ignorada_en_tests_o_examples():
    token = "sk-proj-" + ("Z9qR2mS7" * 5)
    for path in ["tests/test_example.py", ".env.example", "backend/tests/test_audita_secrets_repo.py"]:
        found = scanner._escaneja_text('API_KEY="'+token+'"', path, "arbre", estricte=True)
        assert found
        assert any(scanner.severitat_de(t.tipus,t.classificacio,t.ruta,t.zona,
                   versionat=True,placeholder=t.sembla_plantilla,material_fort=t.material_fort,
                   estricte=True) == scanner.SEV_BLOQUEJANT for t in found)
        assert token not in json.dumps([t.dict() for t in found])

def test_literal_amb_paraula_dummy_no_silencia_secret():
    token = "sk-proj-" + ("Z9qR2mS7" * 3) + "dummy" + ("K8xY4cT1" * 3)
    found=scanner._escaneja_text(token,"docs/example.md","historial",estricte=True)
    assert found
    assert scanner.severitat_de(found[0].tipus, found[0].classificacio,
        found[0].ruta, found[0].zona, versionat=True, placeholder=True,
        estricte=True) == scanner.SEV_BLOQUEJANT

def test_nomes_versionats_no_llegeix_env_local(tmp_path,monkeypatch):
    subprocess.run(["git","init",str(tmp_path)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    (tmp_path/"code.py").write_text("x = 1",encoding="utf-8")
    (tmp_path/".gitignore").write_text(".env\n",encoding="utf-8")
    (tmp_path/".env").write_text("not-to-be-read",encoding="utf-8")
    subprocess.run(["git","-C",str(tmp_path),"add","code.py",".gitignore"],check=True)
    real_open = open
    def guarded(file,*args,**kwargs):
        assert Path(file).name != ".env"
        return real_open(file,*args,**kwargs)
    monkeypatch.setattr("builtins.open",guarded)
    found,metadata=scanner.escaneja_arbre(str(tmp_path),mida_max=100000,
        estricte=True,nomes_versionats=True)
    assert not found and metadata["fitxers_escanejats"] == 2



@pytest.mark.parametrize("statement", [
    "INSERT INTO alumnes (id, nom) VALUES\n('synthetic-id', 'synthetic-name');",
    "INSERT INTO alumnes\n(id, nom)\nVALUES\n('synthetic-id', 'synthetic-name');",
    "INSERT INTO alumnes (id, nom) VALUES\n('synthetic-id', 'first;synthetic-name');",
    "INSERT INTO alumnes (id, nom) VALUES\n('synthetic-id', 'first'';synthetic-name');",
    "INSERT INTO alumnes (id, nom) VALUES\n('synthetic-id', E'first\\';synthetic-name');",
    "INSERT INTO alumnes (id, nom) VALUES\n('synthetic-id', $$first;synthetic-name$$);",
    "INSERT INTO alumnes (id, nom) VALUES /* outer; /* nested; */ still; */\n('synthetic-id', 'synthetic-name');",
    "COPY public.alumnes (id, nom) FROM stdin;\nsynthetic-id\tsynthetic-name\n\\.\n",
])
def test_sql_multilinia_excepcio_no_aprova_contingut_canviat(tmp_path, statement):
    source = tmp_path / "seed.sql"
    source.write_text(statement, encoding="utf-8")
    kwargs = dict(fer_arbre=True, fer_historial=False, mida_max=1_000_000, estricte=True)
    initial = scanner.construeix_informe(str(tmp_path), **kwargs)
    finding = next(t for t in initial["troballes"] if t["tipus"] == "dump_sql_pii")
    rule = f"{finding['fingerprint']}:dump_sql_pii:seed.sql=SYNTHETIC-REVIEW"
    approved = scanner.construeix_informe(str(tmp_path), permesos_pii=[rule], **kwargs)
    assert approved["net"]
    source.write_text(statement.replace("synthetic-name", "synthetic-changed"), encoding="utf-8")
    changed = scanner.construeix_informe(str(tmp_path), permesos_pii=[rule], **kwargs)
    assert not changed["net"]
    assert changed["resum"]["ignorades_per_llista_blanca"] == 0
    changed_finding = next(t for t in changed["troballes"] if t["tipus"] == "dump_sql_pii")
    assert changed_finding["fingerprint"] != finding["fingerprint"]
    serialised = json.dumps(changed)
    assert "synthetic-id" not in serialised and "synthetic-changed" not in serialised


def test_sql_fingerprint_inclou_ultima_fila_despres_de_bloc_gran():
    prefix = "INSERT INTO alumnes (id, nom) VALUES\n('synthetic-id', '" + "padding" * 20_000 + "'),\n"
    old = prefix + "('synthetic-last', 'synthetic-name');"
    new = prefix + "('synthetic-last', 'synthetic-changed');"
    findings_old = scanner._escaneja_text(old, "seed.sql", "historial", estricte=True)
    findings_new = scanner._escaneja_text(new, "seed.sql", "historial", estricte=True)
    old_fp = next(t.fingerprint for t in findings_old if t.tipus == "dump_sql_pii")
    new_fp = next(t.fingerprint for t in findings_new if t.tipus == "dump_sql_pii")
    assert old_fp != new_fp
