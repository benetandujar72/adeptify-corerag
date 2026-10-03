"""CLI: auditor READ-ONLY de secrets i PII d'un repositori (working tree + HISTORIAL de git).

Per què existeix: esborrar del working tree un fitxer amb credencials **no en treu res de
l'historial**. El blob segueix dins `.git` i qualsevol clon —present o futur— el pot
recuperar amb `git cat-file`. Per això aquest escàner mira les DUES zones i, a més, recorre
els objectes **penjants** (unreachable): un `git commit --amend` o un `reset` deixen el blob
amb el secret viu a la base d'objectes encara que ja no el referenciï cap branca.

Serveix com a **criteri de sortida de la Fase 0** d'integració i com a gate de CI. Com que
serveix de gate, la propietat que més importa NO és detectar molt, sinó **no dir mai NET quan
no s'ha pogut mirar**. D'aquí les tres regles del fitxer:

1. **Un mode demanat que no es pot executar és un ERROR (exit 2), mai un `NET`.** Si es demana
   `--historial` i falta `git`, o el clon és *shallow*/parcial, o `cat-file` peta, l'informe
   surt amb `auditoria_completa=False` i codi 2. Degradar silenciosament a `--arbre` (el que
   feia la versió anterior) convertia el gate en una màquina de falsos negatius: un
   `git clone --mirror` (repo BARE, sense working tree) donava `exit 0` amb el repo ple de claus.
2. **El que no s'ha mirat es reporta com a troballa.** Un fitxer o blob descartat per mida
   genera una troballa `no_auditat_per_mida`: un `pg_dump` de 7 MB amb files d'`alumnes` no pot
   sortir com a "NET" només perquè és gran.
3. **Fail-closed a la classificació.** Si d'un blob no en sabem la ruta (objecte penjant), no
   es pot descartar cap detector "per ruta": s'apliquen TOTS. Sense ruta no es pot descartar res.

REGLA ABSOLUTA — aquest script NO imprimeix MAI el material sensible.
De cada troballa només surt: ruta, commit curt, número de línia, tipus i un **fingerprint**
(sha256 truncat a 12 hex) que permet correlacionar dues troballes (mateixa clau a dos
fitxers/repos) sense revelar-ne ni un fragment. La raó és òbvia però es documenta perquè és
la invariant del fitxer: l'informe està pensat per enganxar-se a un tiquet, a un log de CI o
a un correu al DPD; si filtrés el secret que denuncia, l'auditoria mateixa seria l'incident.

El **fingerprint deriva sempre del MATERIAL**, mai d'una etiqueta. És el que fa que la llista
blanca `--permet-fp` sigui segura: si es derivés del nom de la taula (`alumnes`), silenciar un
seed sintètic silenciaria *tots* els dumps de menors del repo amb un sol fingerprint.

Ús:
    python -m scripts.audita_secrets_repo --repo /ruta/al/repo
    python -m scripts.audita_secrets_repo --repo /ruta/al/repo --historial --informe informe.json
    python -m scripts.audita_secrets_repo --repo /ruta/al/clon.git --historial   # bare/mirror

Sense `--arbre` ni `--historial` s'executen tots dos modes (en un repo BARE només l'historial,
perquè no hi ha working tree).

Codis de sortida:
    0  net (cap troballa **dels patrons coberts**) i auditoria completa
    1  hi ha troballes  → la Fase 0 NO es pot donar per tancada
    2  l'auditoria NO s'ha pogut completar (git absent, clon shallow/parcial, repo inexistent,
       mode demanat inaplicable, informe no escrivible) → tampoc es pot tancar la Fase 0

Dependències: només stdlib (+ `git` per l'historial). És deliberat: aquest escàner ha de
poder córrer sobre un repo de tercers, en una màquina neta i sense instal·lar res.
"""

from __future__ import annotations

import argparse
import base64
import bz2
import glob
import gzip
import hashlib
import io
import json
import lzma
import os
import re
import subprocess
import sys
import zipfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone

# Arrel per defecte: scripts/ -> backend/ -> adeptify-suiterag/. Auditar-se un mateix ha de
# ser el cas trivial (no cal recordar cap ruta per passar el gate al propi repo).
_ARREL_DEFECTE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Límit de mida per blob/fitxer. Es va pujar de 5 MB a 100 MB perquè el límit baix descartava
# EXACTAMENT els artefactes que concentren PII massiva: un `pg_dump` real de 4 xifres d'alumnes
# passa dels 5 MB amb facilitat i quedava fora de l'informe sense deixar rastre. Ara, a més, el
# que se salta el límit **surt com a troballa** (`no_auditat_per_mida`), no com a silenci.
_MIDA_MAX_MB_DEFECTE = 100.0

# Directoris que mai contenen secrets propis del projecte i sí milions de fitxers de tercers.
# `.git` NO hi és com a "zona prohibida" sinó com a directori que no es recorre sencer (són
# objectes zlib): d'ell se n'escanegen explícitament els fitxers de text de `_FITXERS_GIT`,
# perquè `.git/config` sol portar credencials dins la URL del remote.
_DIRS_OMESOS = frozenset(
    {
        ".git",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        "env",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".next",
        ".svelte-kit",
        "dist",
        "build",
        "coverage",
        ".markitdown",
    }
)

# Fitxers de text de dins `.git` que sí que s'auditen. `config` és el important: la URL del
# remote amb credencials incrustades (`https://<usuari>:<token>@github.com/...`) hi viu en clar
# i cap escàner que ignori `.git` la veurà mai.
_FITXERS_GIT = ("config", "packed-refs", "COMMIT_EDITMSG", "FETCH_HEAD", "description")

# Fragments de ruta que marquen un fitxer com a "de risc": si un d'aquests no s'ha pogut
# auditar (il·legible), és una troballa i no una nota al peu.
_PATRONS_RUTA_RISC = (
    ".sql",
    "backup",
    "dump",
    ".env",
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    "credential",
    "secret",
    "service-account",
    "service_account",
)

# Taules que, en un dump SQL, impliquen PII de persones (menors incloses). No cal encertar-les
# totes: n'hi ha prou amb una per marcar el dump com a "no pot viure al repo".
_TAULES_PII = (
    "alumnes",
    "alumne",
    "alumnos",
    "students",
    "pf",
    "families",
    "familia",
    "vincle_familia_alumne",
    "tutories_alumne",
    "entrevistes",
    "notes_tutoria",
    "persones",
    "personal_fitxa",
    "usuaris",
    "usuarios",
    "users",
)

# Classificacions. `pii_menors` té un règim de silenciament separat: no es pot amagar amb
# `--permet-fp`, cal `--permet-pii FP=TIQUET` (amb referència escrita).
CLAS_CREDENCIAL = "credencial"
CLAS_PII_MENORS = "pii_menors"
CLAS_NO_AUDITAT = "no_auditat"

# ── Severitat: el que decideix si el GATE bloqueja ────────────────────────────
# Sense aquesta capa l'eina detecta bé però és inservible com a porta: sobre un repo sa
# donava 69 troballes i exit 1, de manera que el criteri «exit code 0» era inabastable i
# el gate acabava ignorat (el mode de fallada clàssic de la tooling de seguretat).
# La detecció NO es toca: es classifica.
SEV_BLOQUEJANT = "bloquejant"  # secret/PII de debò i VERSIONAT → la Fase 0 no es pot tancar
SEV_AVIS = "avis"              # troballa real però no bloquejant (baixa confiança o no versionada)
SEV_INFO = "informatiu"        # soroll conegut: fixtures del propi test, marcadors de plantilla

# Tipus de baixa confiança: casen per la FORMA (`X = "..."` amb un nom que sona a secret) i
# encerten tant una contrasenya com una variable anomenada `token` o la paraula «secrets» en
# prosa. Són útils per revisar, mai per bloquejar.
_TIPUS_BAIXA_CONFIANCA = frozenset({"secret_generic_assignat"})

# Fitxers que contenen material sintètic PER DISSENY: les proves del propi auditor. Marcar-les
# com a troballa és auto-denúncia i garanteix que el gate no arribi mai a verd.
_RUTES_MATERIAL_SINTETIC = ("backend/tests/test_audita_secrets_repo.py",)

# Marcadors de PLANTILLA dins d'un valor compost. `_RE_PLACEHOLDER` està ancorada (^...$) i
# només casa quan TOT el valor és un marcador, així que se li escapava el cas real
# `123456789:AAExEMPLE-token-fictici-no-el-comparteixis` d'un runbook: un token d'exemple que
# feia saltar el gate i enviava a revocar una credencial inexistent.
_RE_MARCADOR_INTERN = re.compile(
    r"(?i)(exemple|example|ejemplo|fictici|ficticio|fictitious|placeholder|dummy|sample"
    r"|changeme|change[-_]me|redacted|redactat|no[-_]el[-_]comparteixis|posa[-_]hi"
    # «no cal», «sense clau», «not needed»: el valor DIU que no és una credencial. Passa amb
    # els clients OpenAI apuntats a Ollama, que exigeixen el camp però ignoren el valor.
    r"|no[-_]cal|sense[-_]clau|cap[-_]clau|not[-_]needed|unused|no[-_]aplica"
    # NOTA: `123456789` NO hi és a posta, tot i ser l'id de bot canònic de la documentació.
    # Com que això casa per SUBCADENA, un token REAL amb un id que comenci per aquests dígits
    # (p. ex. `1234567890:AA…`) quedaria silenciat: un fail-open. El cas del runbook ja el
    # capturen `exemple` i `fictici`, que són marcadors inequívocs.
    r"|xxxxx|aaaaaa|<[^>]{3,}>)"
)

# Fitxers que existeixen PER contenir valors d'exemple. Marcar-hi un secret és confondre el
# propòsit del fitxer amb una fuita; el risc real seria que algú hi posés el valor de debò,
# així que es degraden a AVÍS (visibles) i no a informatiu.
_SUFIXOS_FITXER_EXEMPLE = (".example", ".sample", ".template", ".dist", ".defaults")


def _es_ruta_exemple(ruta: str) -> bool:
    base = ruta.replace("\\", "/").lower().rsplit("/", 1)[-1]
    return base.endswith(_SUFIXOS_FITXER_EXEMPLE)


# Extensions de membres d'arxiu que són binaris per definició (imatges, tipografies,
# multimèdia, objectes incrustats). No s'escanegen com a text: només generen coincidències
# a l'atzar. La detecció real de secrets dins d'un .docx viu al seu XML, que sí que es mira.
_EXTENSIONS_MEMBRE_BINARI = (
    ".jpeg", ".jpg", ".png", ".gif", ".bmp", ".ico", ".tiff", ".webp",
    ".emf", ".wmf", ".ttf", ".otf", ".woff", ".woff2", ".eot",
    ".mp3", ".mp4", ".wav", ".avi", ".mov", ".pdf", ".bin",
)


def _es_membre_binari(nom: str) -> bool:
    return nom.lower().rsplit("/", 1)[-1].endswith(_EXTENSIONS_MEMBRE_BINARI)


def _sembla_fila_de_dades(text: str) -> bool:
    """Cert si un `INSERT INTO <taula_pii>` porta DADES, no només noms de columnes.

    Sense això, el detector marcava com a «dump amb PII de menors» les funcions PL/pgSQL de
    migració (`INSERT INTO public.alumnes (id, nom, cognoms, …)` amb `VALUES (v_id, v_nom, …)`
    a la línia següent): codi de trigger amb VARIABLES, zero files reals. Eren 3 dels 6
    bloquejants sobre un repo sa, i un gate que crida el llop no el mira ningú.

    El cridador passa el statement complet, incloses les files multilínia.
    Criteri conservador:
      · `COPY` → cert: les files van a les línies següents (pg_dump en format text);
      · literal citat (`'…'`) a la mateixa línia → cert: hi ha dades;
      · `VALUES` a la mateixa línia → cert: insert d'una sola línia amb dades;
      · només llista de columnes → fals.
    Limitació acceptada i explícita: un INSERT d'una sola línia amb dades EXCLUSIVAMENT
    numèriques i sense `VALUES` capturat no es marcaria; per a taules de persones (noms,
    cognoms, adreces) el cas pràctic sempre porta literals citats."""
    t = text.lstrip()
    if t[:4].upper() == "COPY":
        return True
    return "'" in t or re.search(r"(?i)\bVALUES\b", t) is not None


def _material_sql(contingut: str, inici: int) -> str:
    """Statement complet; COPY inclou les files fins al terminador de pg_dump.

    El fingerprint no pot dependre només del capçal/columnes d'un INSERT
    multilínia. No truncar el material: afegir una fila després d'un límit
    fix no pot reutilitzar una excepció aprovada per a contingut diferent.
    """
    i, final = inici, len(contingut)
    while i < len(contingut):
        if contingut.startswith("--", i):
            salt = contingut.find("\n", i + 2)
            i = len(contingut) if salt < 0 else salt + 1
            continue
        if contingut.startswith("/*", i):
            profunditat = 1
            i += 2
            while i < len(contingut) and profunditat:
                if contingut.startswith("/*", i):
                    profunditat += 1
                    i += 2
                elif contingut.startswith("*/", i):
                    profunditat -= 1
                    i += 2
                else:
                    i += 1
            continue
        if contingut[i] in "'\"\x60":
            cometa = contingut[i]
            i += 1
            while i < len(contingut):
                if contingut[i] == "\\":
                    i += 2  # E-strings/MySQL; conservador si el dialecte no escapa.
                elif contingut[i] == cometa:
                    if i + 1 < len(contingut) and contingut[i + 1] == cometa:
                        i += 2
                    else:
                        i += 1
                        break
                else:
                    i += 1
            continue
        if contingut[i] == "$":
            etiqueta = re.match(r"\$(?:[A-Za-z_][A-Za-z_0-9]*)?\$", contingut[i:])
            if etiqueta:
                delimitador = etiqueta.group(0)
                tancament = contingut.find(delimitador, i + len(delimitador))
                i = len(contingut) if tancament < 0 else tancament + len(delimitador)
                continue
        if contingut[i] == ";":
            final = i + 1
            break
        i += 1
    statement = contingut[inici:final]
    if re.match(r"(?i)COPY\b", statement) and re.search(r"(?i)\bFROM\s+stdin\b", statement):
        terminador = re.search(r"(?m)^\\\.\r?$", contingut[final:])
        final = len(contingut) if terminador is None else final + terminador.end()
    return contingut[inici:final]


def _conte_marcador_placeholder(material: str) -> bool:
    """Cert si el material duu un marcador de plantilla EVIDENT com a subcadena.

    Complementa `_RE_PLACEHOLDER` (que exigeix que el valor sencer sigui el marcador) per als
    valors compostos de documentació. Fail-safe deliberat: NO esborra la troballa, només la
    degrada a informativa — si l'heurística s'equivoca, la troballa segueix sortint a l'informe."""
    return bool(_RE_MARCADOR_INTERN.search(material or ""))


def _es_ruta_de_prova(ruta: str) -> bool:
    """Cert si la ruta és de codi de PROVA (fixtures amb credencials falses per disseny).

    Deliberadament estricte: només `tests/` com a component de ruta o un fitxer `test_*.py` /
    `*_test.py`. No es filtra per la subcadena «test» a qualsevol lloc, que engoliria coses com
    `protesta.py` o un directori `latest/`."""
    r = ruta.replace("\\", "/").lower()
    base = r.rsplit("/", 1)[-1]
    return (
        "/tests/" in f"/{r}"
        or r.startswith("tests/")
        or (base.startswith("test_") and base.endswith(".py"))
        or base.endswith("_test.py")
    )


# Un material «fort» té prou llargada i barreja per ser una credencial de debò, i no el nom
# d'una variable. Llindar deliberadament baix (12 i 2 classes): `b7f3a91c4d2e8a05` és hex de
# 16 i ha de bloquejar; `token`/`appendtoken` no hi arriben.
_LLARG_MIN_MATERIAL_FORT = 12
_CLASSES_MIN_MATERIAL_FORT = 2


def _es_material_fort(material: str) -> bool:
    m = material or ""
    # Una URL no és una credencial. `token_uri = "https://oauth2.googleapis.com/token"` és
    # l'ENDPOINT d'OAuth, i és llarg i mixt: sense aquesta regla passava per credencial forta.
    if "://" in m:
        return False
    # Amb espais és PROSA, no un token: la paraula «secrets» dins d'una frase d'un document
    # arrossegava la resta de la línia i es promovia a bloquejant.
    if any(c.isspace() for c in m):
        return False
    # Una RUTA DE FITXER no és una credencial: `Secrets: rag-service/.env` capturava el camí
    # citat en un document. Es reconeix per l'extensió final; les claus base64 (que també poden
    # dur `/`) no acaben en `.env`/`.json`/`.pem`.
    if re.search(r"\.[A-Za-z]{2,5}$", m) and ("/" in m or "\\" in m or m.startswith(".")):
        return False
    # Referència a un gestor de secrets (`NOM:latest`, `NOM:3`), no el secret. És el patró de
    # `gcloud run --set-secrets="X=X:latest"`. NO pot col·lidir amb un token de Telegram
    # (`123456789:AA…`), que porta ≥30 caràcters aleatoris després dels dos punts.
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*:(?:latest|\d{1,4})", m):
        return False
    return (
        len(m) >= _LLARG_MIN_MATERIAL_FORT
        and _classes_caracters(m) >= _CLASSES_MIN_MATERIAL_FORT
    )


def severitat_de(tipus: str, classificacio: str, ruta: str, zona: str, *, versionat: bool,
                 placeholder: bool, pot_determinar_versionat: bool = False,
                 material_fort: bool = True, estricte: bool = False) -> str:
    """Severitat d'una troballa. L'ordre de les regles és el criteri de seguretat.

    Regla de fons: **el que fa mal és el secret VERSIONAT**. Un `.env` gitignored amb la
    contrasenya de producció és el patró CORRECTE (és on ha de viure); reportar-lo és útil com a
    inventari, però bloquejar-hi el desplegament és soroll. En canvi, el mateix valor dins d'un
    commit és recuperable per qualsevol que cloni: això sí que atura la Fase 0."""
    if estricte:
        if classificacio == CLAS_NO_AUDITAT:
            return SEV_BLOQUEJANT
        if tipus not in _TIPUS_BAIXA_CONFIANCA or material_fort:
            return SEV_BLOQUEJANT
        return SEV_AVIS
    if any(ruta.endswith(s) for s in _RUTES_MATERIAL_SINTETIC):
        return SEV_INFO  # fixtures del propi auditor
    if placeholder:
        return SEV_INFO  # marcador de documentació, no una credencial
    if classificacio == CLAS_NO_AUDITAT:
        return SEV_BLOQUEJANT  # «no ho he pogut mirar» mai és verd (pot amagar PII massiva)
    # Tipus de baixa confiança: NO es degraden en bloc. El que decideix és el MATERIAL —
    # `SESSION_SECRET=<valor llarg i aleatori>` és una credencial de debò i ha de bloquejar, mentre que
    # una variable anomenada `token` (curta i d'una sola classe de caràcters) és soroll. Vetar
    # el tipus sencer amagava el primer cas, que és precisament el que aquests detectors busquen.
    if tipus in _TIPUS_BAIXA_CONFIANCA and not material_fort:
        return SEV_AVIS
    # Fitxers de PROVA: contenen credencials falses per disseny (un test d'OAuth necessita un
    # `client_secret`). Es degraden a AVÍS, no a informatiu: segueixen ben visibles a l'informe
    # perquè algú hi podria enganxar una credencial real, però no aturen el desplegament.
    if _es_ruta_de_prova(ruta) or _es_ruta_exemple(ruta):
        return SEV_AVIS
    # Una troballa a l'HISTORIAL és versionada per definició: no depenem que el cridador ho
    # calculi bé (equivocar-s'hi aquí seria un fals NEGATIU, el pitjor error d'aquesta eina).
    if zona == "historial":
        return SEV_BLOQUEJANT
    # La rebaixa «no versionat → avís» NOMÉS és legítima si SABEM què hi ha a git. Sobre un
    # directori que no és repo (una exportació, una còpia, un context de build) no es pot
    # distingir, i presumir «no versionat» faria que un secret real hi passés com a avís:
    # un FAIL-OPEN. Sense manera de determinar-ho, bloqueja.
    if pot_determinar_versionat and not versionat:
        return SEV_AVIS  # existeix al disc però no a git: inventari, no exposició per clonatge
    return SEV_BLOQUEJANT

# Valors que semblen secret però són marcadors de plantilla. Es filtren per no ofegar
# l'informe real amb soroll de `.env.example`. La llista és **tancada** a propòsit: l'alternativa
# antiga `(?:your|my|the)[-_ ]?\w*` era golafre fins a l'absurd (engolia `mysupersecretvalue` i
# `theRealProdSecret`, és a dir contrasenyes reals) i s'ha substituït per parells
# prefix+terme explícits.
_RE_PLACEHOLDER = re.compile(
    r"""^(?:
          x+ | \.+ | -+ | \*+
        | (?:your|my|the|el|teu|tu|un)[-_ ]?
          (?:secret|key|token|password|passwd|pass|api[-_ ]?key|client[-_ ]?secret
             |private[-_ ]?key|value|clave|clau|contrasenya)[-_ ]?\w*
        | (?:change|replace)[-_ ]?(?:me|this)\w*
        | (?:place)?holder\w* | example\w* | sample\w* | dummy\w* | fake\w*
        | redacted\w* | secret | password | passwd | pass | token | apikey | api[-_]key
        | tu[-_ ]?\w*secret\w* | posa[-_ ]?\w+
    )$""",
    re.IGNORECASE | re.VERBOSE,
)


# Cadena d'identificadors tipus `google_client_secret`, `os.environ.get`, `process.env.X`.
_RE_CADENA_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*")

# Termes que delaten que un identificador és el NOM de la cosa buscada, no el seu valor.
_RE_TERMES_SECRET = re.compile(
    r"(?i)secret|password|passwd|token|api[-_]?key|credential|private[-_]?key|clau|contrasenya|clave"
)


def _declarat_com_a_identificador(valor: str, contingut: str) -> bool:
    """Cert si `valor` apareix al MATEIX fitxer com a nom de variable, no com a dada.

    És la forma honesta de decidir "això és una referència, no un secret": si el text que hem
    capturat també surt com a `${VALOR}`, `process.env.VALOR`, `os.environ["VALOR"]` o com a
    clau declarada en una altra línia, aleshores el que hem vist és un **nom** i el secret real
    viu fora del fitxer (que és el patró correcte). Sense aquesta evidència no es descarta res.
    """
    esc = re.escape(valor)
    patrons = (
        rf"\$\{{?{esc}\b",
        rf"\{{\{{\s*{esc}\s*\}}\}}",
        rf"process\.env\.{esc}\b",
        rf"process\.env\[\s*[\"']{esc}[\"']\s*\]",
        rf"os\.(?:environ|getenv)\s*[\[\(]\s*[\"']{esc}[\"']",
        rf"^\s*(?:export\s+)?{esc}\s*[:=]",
    )
    return any(re.search(p, contingut, re.MULTILINE) for p in patrons)


def _sembla_referencia_codi(valor: str, contingut: str = "") -> bool:
    """Cert si el valor capturat és una referència de codi, no un literal amb el secret.

    `client_secret=google_client_secret` o `client_secret: os.environ.get` són el patró
    CORRECTE (el secret viu fora del fitxer) i marcar-los inundaria l'informe de soroll.

    **La càrrega de la prova està invertida respecte de la versió anterior.** Abans es
    descartava per una heurística de FORMA ("no barreja majúscules, minúscules i xifres → deu
    ser un nom de variable"), i això feia invisibles la majoria de contrasenyes reals:
    `patufet2025`, `contrasenyasegura`, `a1b2c3d4e5f60718`… Ara només es descarta amb evidència
    positiva que és un nom:
      1. és un camí amb punts (`os.environ.get`, `process.env.X`, `settings.CLIENT_SECRET`);
      2. és un identificador amb separadors que **cita el terme buscat** (`google_client_secret`);
      3. el mateix fitxer el declara en una altra línia com a variable.
    Qualsevol altra cosa es reporta. Fail-closed: preferim un fals positiu revisable a mà que una
    contrasenya de producció invisible per sempre.
    """
    v = valor.strip().strip("\"'")
    if not _RE_CADENA_IDENT.fullmatch(v):
        return False  # té `-`, `/`, `+`… → no és un identificador: es tracta com a secret
    if "." in v:
        return True  # camí amb punts → accés a configuració/entorn
    if "_" in v and _RE_TERMES_SECRET.search(v):
        return True  # `google_client_secret`: el valor és el NOM de la clau, no la clau
    return bool(contingut) and _declarat_com_a_identificador(v, contingut)


def _es_placeholder(valor: str, contingut: str = "") -> bool:
    """Cert si el valor capturat és un marcador de plantilla i no un secret real.

    Es descarta també qualsevol valor amb interpolació (`${VAR}`, `{{var}}`, `<...>`):
    això és exactament el patró CORRECTE (secret a variable d'entorn) i marcar-lo com a
    incident penalitzaria el codi ben fet.
    """
    v = valor.strip().strip("\"'")
    if not v:
        return True
    if "${" in v or "{{" in v or (v.startswith("<") and v.endswith(">")):
        return True
    if v.startswith("$") and len(v) > 1 and (v[1].isalpha() or v[1] == "{"):
        return True
    if _RE_PLACEHOLDER.match(v):
        return True
    return _sembla_referencia_codi(v, contingut)


def _classes_caracters(valor: str) -> int:
    """Quantes classes de caràcter (minúscula, majúscula, xifra, símbol) hi ha al valor."""
    v = valor.strip().strip("\"'")
    return sum(
        (
            any(c.islower() for c in v),
            any(c.isupper() for c in v),
            any(c.isdigit() for c in v),
            any(not c.isalnum() for c in v),
        )
    )


def _jwt_privilegiat(text: str) -> bool:
    """Cert si el JWT capturat porta un rol privilegiat a la càrrega útil.

    Un JWT qualsevol en un repo sol ser un fixture de test i marcar-los tots seria soroll. Però
    la clau `service_role` de Supabase **salta el RLS**: dona accés total a la base de dades,
    inclosa la de menors. Es descodifica només la càrrega (base64url, sense verificar signatura:
    no cal, aquí no s'autentica res) i es mira si hi surt un rol d'aquests.
    """
    parts = text.split(".")
    if len(parts) < 2:
        return False
    carrega = parts[1]
    try:
        dades = base64.urlsafe_b64decode(carrega + "=" * (-len(carrega) % 4))
    except Exception:  # noqa: BLE001 — base64 invàlid: no és un JWT que puguem classificar
        return False
    text_carrega = dades.decode("utf-8", errors="replace")
    return bool(
        re.search(r"(?i)service_role|\"role\"\s*:\s*\"(?:admin|owner|service_role)\"", text_carrega)
    )


@dataclass(frozen=True)
class Detector:
    """Un patró de detecció.

    `grup` diu quin grup del regex conté el material sensible: és el que es passa pel
    fingerprint i el que MAI s'imprimeix. `detall_grup`, si existeix, és un grup que sí que
    es pot mostrar perquè per definició no és PII ni credencial (p. ex. el nom d'una taula).
    """

    tipus: str
    patro: re.Pattern[str]
    grup: int = 0
    detall_grup: int | None = None
    detall_etiqueta: str = ""
    filtra_placeholder: bool = False
    classificacio: str = CLAS_CREDENCIAL
    # Si s'omple, el detector només s'aplica a rutes que continguin algun d'aquests fragments.
    # S'avalua contra TOTES les rutes conegudes del blob (un dump commitejat també com a `a.txt`
    # no queda exempt) i **no s'aplica** si no en coneixem cap (objecte penjant): sense ruta no
    # es pot descartar res.
    nomes_si_ruta: tuple[str, ...] = ()
    # Si s'omple, el detector només dispara si el MATEIX contingut conté també aquest patró.
    # Serveix per als marcadors que sols no proven res (p. ex. la cadena "service_account"
    # dins un test amb un JSON buit): sense la clau al costat no hi ha exposició.
    requereix_tambe: re.Pattern[str] | None = None
    # Mínim de caràcters de l'alfabet base64 que ha de tenir el material perquè sigui una
    # clau de debò. Distingeix `-----BEGIN PRIVATE KEY-----\nYOUR_KEY_HERE\n-----END...`
    # (documentació, cap exposició) d'una clau real (centenars de caràcters de base64).
    min_cos_base64: int = 0
    # Mínim de classes de caràcter del material (només per als detectors genèrics, que si no
    # dispararien amb qualsevol paraula).
    min_classes_caracters: int = 0
    # Validació semàntica del text sencer capturat (p. ex. descodificar un JWT i mirar-ne el rol).
    validador: Callable[[str], bool] | None = None


DETECTORS: tuple[Detector, ...] = (
    Detector(
        tipus="clau_privada_pem",
        # Cobreix RSA/EC/OPENSSH/PKCS#8. Es captura el COS (grup 1), no la capçalera: si el
        # fingerprint es calculés sobre `-----BEGIN PRIVATE KEY-----` seria idèntic per a
        # totes les troballes i no serviria per correlacionar res. La classe de caràcters és
        # l'alfabet base64 + espais + la barra dels `\n` escapats, així que s'atura sola al
        # `-----END` (o al text que segueixi un marcador de plantilla).
        patro=re.compile(r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----([A-Za-z0-9+/=\\\s]*)"),
        grup=1,
        min_cos_base64=40,
    ),
    Detector(
        tipus="service_account_json",
        patro=re.compile(r"\"type\"\s*:\s*\"service_account\""),
        # Només si la clau hi és de debò: el marcador sol apareix a tests i a documentació.
        requereix_tambe=re.compile(r"private_key|-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----"),
    ),
    Detector(
        tipus="service_account_private_key",
        # El camp `private_key` d'una clau de service-account, amb el PEM escapat (\n literals).
        patro=re.compile(r"\"?private_key\"?\s*[:=]\s*[\"']([^\"']{16,})"),
        grup=1,
        filtra_placeholder=True,
        # Llindar alt: el material capturat inclou la capçalera PEM (que ja aporta ~15
        # caràcters), i cap plantilla de documentació hi arriba; una clau real el supera per
        # un ordre de magnitud.
        min_cos_base64=100,
    ),
    Detector(
        tipus="client_secret",
        patro=re.compile(r"(?i)\bclient[_-]?secret[\"']?\s*[:=]\s*[\"']?([A-Za-z0-9_\-./+]{8,})"),
        grup=1,
        filtra_placeholder=True,
    ),
    Detector(
        tipus="client_secret_google",
        # `GOCSPX-` és el prefix del VALOR, no una clau seguida de `[:=]`. La versió anterior
        # el posava dins l'alternativa de `client_secret` exigint `GOCSPX[:=]`, cosa que no
        # existeix enlloc: era codi mort i cap test se n'adonava.
        patro=re.compile(r"\bGOCSPX-[A-Za-z0-9_\-]{20,}"),
    ),
    Detector(
        tipus="token_bot_telegram",
        patro=re.compile(r"\b\d{6,}:[A-Za-z0-9_-]{30,}\b"),
    ),
    Detector(
        tipus="clau_api_openai",
        patro=re.compile(r"\bsk-(?:proj-|ant-|live-)?[A-Za-z0-9_\-]{20,}\b"),
    ),
    Detector(
        tipus="clau_api_google",
        # Les claus canòniques són AIza + 35 caràcters, però es fa servir `{35,}` per no
        # deixar passar variants més llargues: fail-closed davant un format que canviï.
        patro=re.compile(r"\bAIza[0-9A-Za-z_\-]{35,}"),
    ),
    Detector(
        tipus="clau_aws",
        patro=re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    ),
    Detector(
        tipus="token_github",
        # PAT clàssic (`ghp_`) i els seus germans (oauth/user/server/refresh) + PAT fine-grained.
        patro=re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{20,})\b"),
    ),
    Detector(
        tipus="token_slack",
        patro=re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    ),
    Detector(
        tipus="clau_stripe",
        patro=re.compile(r"\b[sr]k_live_[A-Za-z0-9]{16,}\b"),
    ),
    Detector(
        tipus="jwt_rol_privilegiat",
        # Cas real d'aquesta organització: `SUPABASE_SERVICE_ROLE_KEY`. Un JWT amb rol
        # `service_role` salta el RLS i llegeix la BD sencera, menors inclosos.
        patro=re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
        validador=_jwt_privilegiat,
    ),
    Detector(
        tipus="url_connexio_amb_contrasenya",
        # postgres://user:pass@host — la contrasenya viatja dins la URL i sovint és la de prod.
        patro=re.compile(
            r"\b(?:postgres(?:ql)?|mysql|mariadb|mongodb(?:\+srv)?|redis|rediss|amqps?)://"
            r"[^\s:/@\"']+:([^\s:/@\"']{3,})@"
        ),
        grup=1,
        filtra_placeholder=True,
    ),
    Detector(
        tipus="credencial_dins_url_http",
        # `https://usuari:token@github.com/...`. Viu típicament a `.git/config` i als scripts
        # de desplegament; és una credencial completa en clar.
        patro=re.compile(r"https?://[^\s:/@\"']+:([^\s:/@\"']{3,})@[^\s\"']+"),
        grup=1,
        filtra_placeholder=True,
    ),
    Detector(
        tipus="contrasenya_aplicacio_google",
        # Format de les contrasenyes d'aplicació de Google: 16 lletres minúscules, sovint
        # escrites en grups de 4. Sol, el patró casa amb qualsevol seqüència de 4 paraules curtes
        # de prosa; per això s'exigeix que sigui el VALOR assignat a una clau que s'anomeni així.
        patro=re.compile(
            r"(?i)\b[A-Za-z0-9_]*(?:app[_-]?password|contrasenya[_-]?aplicacio)[\"']?\s*[:=]\s*"
            r"[\"']?\b([a-z]{4}(?: ?[a-z]{4}){3})\b"
        ),
        grup=1,
        filtra_placeholder=True,
    ),
    Detector(
        tipus="secret_generic_assignat",
        # Xarxa d'arrossegament per a les credencials que no tenen prefix reconeixible
        # (`SESSION_SECRET`, `WEBHOOK_SECRET`, `*_PASSWORD`…). El nom de la variable va a
        # `detall` (no és sensible) i el fingerprint, al valor. El valor ha de començar per
        # alfanumèric perquè els `-----BEGIN…` ja els cobreix el detector de PEM.
        patro=re.compile(
            r"(?i)\b([A-Za-z0-9_]*"
            r"(?:secret|password|passwd|api[_-]?key|apikey|access[_-]?token|auth[_-]?token|token)"
            # Els delimitadors (parèntesis, claudàtors, cometes invertides, angles) queden fora
            # del valor: `os.getenv('X')` ha de capturar `os.getenv` —una referència
            # reconeixible— i no `os.getenv(`, que no és cap identificador i per tant es
            # reportaria com si fos una contrasenya.
            r"[A-Za-z0-9_]*)\s*[:=]\s*[\"'`]?([A-Za-z0-9][^\s\"'`#,;()\[\]{}<>]{7,})"
        ),
        grup=2,
        detall_grup=1,
        detall_etiqueta="clau",
        filtra_placeholder=True,
        min_classes_caracters=2,
    ),
    Detector(
        tipus="dump_sql_pii",
        # Dump amb dades de persones. `INSERT INTO` (pg_dump --inserts / mysqldump) i `COPY`
        # (pg_dump text). Només s'aplica a fitxers .sql o sota backups/ per no marcar migracions
        # de codi que citen la taula sense portar-ne cap fila… però si la ruta del blob és
        # DESCONEGUDA (objecte penjant) s'aplica igualment: vegeu `nomes_si_ruta`.
        #
        # El patró localitza el capçal. _escaneja_text obté el statement complet
        # amb _material_sql: el fingerprint inclou els valors de totes les files,
        # també en INSERT multilínia i COPY FROM stdin, no només les columnes.
        patro=re.compile(
            r"(?i)\b(?:INSERT\s+INTO|COPY)\s+[\"`]?(?:public\.)?[\"`]?("
            + "|".join(_TAULES_PII)
            + r")[\"`]?\s*[\(\s]([^\n]*)"
        ),
        grup=2,
        detall_grup=1,
        detall_etiqueta="taula",
        # Exigeix DADES, no una llista de columnes: descarta les funcions de migració/trigger
        # que citen la taula amb variables (vegeu `_sembla_fila_de_dades`).
        validador=_sembla_fila_de_dades,
        classificacio=CLAS_PII_MENORS,
        nomes_si_ruta=(".sql", "backup", "dump"),
    ),
)

# Sostre de troballes del mateix tipus dins un mateix fitxer/blob. Un dump amb 4.000 files
# generaria 4.000 troballes i faria l'informe inservible; amb 50 ja se sap tot el que cal
# (el fitxer surt, el veredicte és 1 i la remediació és la mateixa). No és fail-open: el
# recompte real es publica a `ocurrencies_totals`.
_MAX_TROBALLES_PER_FITXER_I_TIPUS = 50


@dataclass
class Troballa:
    """Una troballa ja sanejada: res del que hi ha aquí revela el secret."""

    zona: str  # "arbre" | "historial"
    tipus: str
    ruta: str
    linia: int
    fingerprint: str
    ocurrencies: int = 1
    commits: list[str] = field(default_factory=list)
    blob: str = ""
    detall: str = ""
    classificacio: str = CLAS_CREDENCIAL
    # TOTES les rutes on ha viscut el blob. Es publica la llista, no només el recompte: la via A
    # de remediació (`git filter-repo --path …`) exigeix conèixer-les totes; amb un comptador la
    # llista de `--path` es construeix incompleta i la purga deixa el secret viu.
    rutes: list[str] = field(default_factory=list)
    # Severitat del GATE. Es calcula a `construeix_informe` (cal saber què hi ha a git);
    # per defecte, la més restrictiva: si ningú l'ha classificada, bloqueja.
    severitat: str = SEV_BLOQUEJANT
    # El material capturat duia un marcador de plantilla evident (`EXEMPLE`, `fictici`,
    # `123456789:`…). Es decideix a la DETECCIÓ, que és l'únic lloc on hi ha el material;
    # aquí només se'n desa el booleà, que no revela res. Default `False` = no es presumeix.
    sembla_plantilla: bool = False
    # El material té llargada i barreja de credencial real (no el nom d'una variable). També
    # es decideix a la detecció i només se'n desa el booleà. Default `True` = no es presumeix
    # que sigui soroll (el costat segur).
    material_fort: bool = True

    @property
    def rutes_alternatives(self) -> int:
        return max(0, len(self.rutes) - 1)

    def clau(self) -> tuple[str, str, str, str]:
        return (self.zona, self.ruta, self.tipus, self.fingerprint)

    def dict(self) -> dict:
        return {
            "zona": self.zona,
            "tipus": self.tipus,
            "severitat": self.severitat,
            "classificacio": self.classificacio,
            "ruta": self.ruta,
            "linia": self.linia,
            "fingerprint": self.fingerprint,
            "ocurrencies": self.ocurrencies,
            "commits": self.commits,
            "blob": self.blob,
            "detall": self.detall,
            "rutes": self.rutes,
            "rutes_alternatives": self.rutes_alternatives,
        }


_RE_NO_BASE64 = re.compile(r"[^A-Za-z0-9+/=]")


def _cos_base64(material: str) -> int:
    """Nombre de caràcters de l'alfabet base64 del material (ignorant espais i `\\n` escapats).

    És el senyal barat per separar una clau real d'un marcador de documentació sense haver
    de parsejar el PEM ni, sobretot, sense haver d'imprimir-ne res per decidir-ho.
    """
    return len(_RE_NO_BASE64.sub("", material.replace("\\n", "")))


def _fingerprint(text: str) -> str:
    """sha256 truncat a 12 hex del material sensible.

    Serveix per correlacionar (la mateixa clau apareix a l'arbre i a 4 commits, o al repo A i
    al B) sense publicar-ne res. 12 hex = 48 bits: suficient contra col·lisions accidentals i
    inservible per fer-ne força bruta amb un secret d'alta entropia.
    """
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:12]


def _linia_de(contingut: str, posicio: int) -> int:
    return contingut.count("\n", 0, posicio) + 1


def _escaneja_text(
    contingut: str,
    ruta: str,
    zona: str,
    *,
    rutes: tuple[str, ...] | None = None,
    estricte: bool = False,
) -> list[Troballa]:
    """Aplica els detectors a un text i retorna troballes deduplicades.

    `rutes` és la llista COMPLETA de rutes conegudes del contingut:
      · `None`  → s'usa `(ruta,)` (cas normal del working tree);
      · `()`    → **no en coneixem cap** (objecte penjant) i aleshores `nomes_si_ruta` no pot
                  descartar res: s'apliquen TOTS els detectors. Sense ruta no es pot descartar.
    """
    rutes_conegudes = (ruta,) if rutes is None else tuple(rutes)
    rutes_baixes = tuple(r.lower() for r in rutes_conegudes)
    trobades: dict[tuple[str, str, str, str], Troballa] = {}
    comptador: dict[str, int] = {}
    for det in DETECTORS:
        if det.nomes_si_ruta and rutes_baixes:
            if not any(f in r for r in rutes_baixes for f in det.nomes_si_ruta):
                continue
        if det.requereix_tambe is not None and not det.requereix_tambe.search(contingut):
            continue
        for m in det.patro.finditer(contingut):
            material = m.group(det.grup) if det.grup else m.group(0)
            validacio = m.group(0)
            if det.tipus == "dump_sql_pii":
                material = _material_sql(contingut, m.start())
                validacio = material
            if not material:
                continue
            if det.filtra_placeholder:
                if estricte:
                    valor = material.strip().strip("\"'")
                    citat = m.start(det.grup) > 0 and contingut[m.start(det.grup) - 1] in "\"'"
                    marcador = re.fullmatch(r"(?i)(?:changeme|placeholder|dummy|example|redacted|x{6,}|\$\{[A-Za-z_][A-Za-z0-9_]*\})", valor)
                    referencia = not citat and re.fullmatch(r"(?:os\.(?:environ|getenv)|process\.env|settings|cfg|cos|integracio)\.[A-Za-z0-9_.]+", valor)
                    if not valor or marcador or referencia:
                        continue
                elif _es_placeholder(material, contingut):
                    continue
            if det.min_cos_base64 and _cos_base64(material) < det.min_cos_base64:
                continue
            if det.min_classes_caracters and _classes_caracters(material) < det.min_classes_caracters:
                continue
            if det.validador is not None and not det.validador(validacio):
                continue
            detall = ""
            if det.detall_grup is not None:
                detall = f"{det.detall_etiqueta}={(m.group(det.detall_grup) or '').lower()}"
            t = Troballa(
                zona=zona,
                tipus=det.tipus,
                ruta=ruta,
                linia=_linia_de(contingut, m.start()),
                fingerprint=_fingerprint(material),
                detall=detall,
                classificacio=det.classificacio,
                rutes=list(rutes_conegudes),
                # ÚNIC punt on es pot decidir: aquí tenim el MATERIAL. La troballa no el desa
                # mai (per no retenir secrets), així que la severitat no ho podria avaluar
                # després. Es guarda només el booleà, que no revela res.
                sembla_plantilla=_conte_marcador_placeholder(material),
                material_fort=_es_material_fort(material),
            )
            existent = trobades.get(t.clau())
            if existent is not None:
                # Mateix secret repetit dins el mateix fitxer: es compta, no es duplica.
                existent.ocurrencies += 1
                continue
            if comptador.get(det.tipus, 0) >= _MAX_TROBALLES_PER_FITXER_I_TIPUS:
                continue
            comptador[det.tipus] = comptador.get(det.tipus, 0) + 1
            trobades[t.clau()] = t
    return list(trobades.values())


# ─────────────────────────── descodificació del contingut ───────────────────────────


def _descomprimeix(dades: bytes, limit: int) -> bytes | None:
    """Descomprimeix en memòria gz/bz2/xz/zip fins a `limit` bytes, o None si no ho és.

    Per què: el `.gitignore` que aquest mateix runbook proposa ja reconeix que existeixen
    `*.sql.gz`. Un dump comprimit té bytes NUL, la heurística clàssica el marcava com a binari
    i la PII de menors hi quedava invisible. El límit evita que una bomba de compressió faci
    petar l'auditor (que és un gate de CI, no pot morir).
    """
    try:
        if dades.startswith(b"\x1f\x8b"):
            with gzip.GzipFile(fileobj=io.BytesIO(dades)) as fh:
                return fh.read(limit)
        if dades.startswith(b"BZh"):
            return bz2.BZ2Decompressor().decompress(dades, limit)
        if dades.startswith(b"\xfd7zXZ\x00"):
            return lzma.LZMADecompressor().decompress(dades, limit)
        if dades.startswith(b"PK\x03\x04"):
            trossos: list[bytes] = []
            total = 0
            with zipfile.ZipFile(io.BytesIO(dades)) as z:
                for info in z.infolist():
                    if info.is_dir() or total >= limit:
                        continue
                    # Els membres BINARIS no s'escanegen com a text. Un .docx/.xlsx és un zip
                    # que porta imatges i miniatures: descodificar-ne els bytes amb
                    # errors="replace" genera mullader en què els patrons casen a l'atzar.
                    # Cas real: la miniatura `docProps/thumbnail.jpeg` d'un manual contenia la
                    # seqüència `456789:…` enmig de taules Huffman i es reportava com a token
                    # de bot — l'ÚNIC bloquejant que quedava sobre un repo sa.
                    # Els membres de TEXT (l'XML del document, un .sql dins d'un zip) sí que
                    # s'escanegen: és tot el sentit de mirar dins dels arxius.
                    if _es_membre_binari(info.filename):
                        continue
                    with z.open(info) as fh:
                        tros = fh.read(limit - total)
                    if _es_binari(tros):
                        continue
                    total += len(tros)
                    trossos.append(tros)
            # Separador entre membres: evita que un patró casi a cavall de dos fitxers
            # concatenats (una coincidència que no existeix en cap dels dos).
            return b"\n".join(trossos)
    except Exception:  # noqa: BLE001 — arxiu corrupte o xifrat: es tracta com a no descomprimible
        return None
    return None


def _a_text(dades: bytes, *, limit: int) -> tuple[str | None, str]:
    """Converteix els bytes en text auditable. Retorna (text, motiu).

    `text is None` vol dir "no s'ha pogut auditar" i `motiu` diu per què.

    La heurística clàssica ("un NUL als primers 8 KiB ⇒ binari") descartava dos casos molt
    reals en aquest entorn: (a) qualsevol fitxer UTF-16 —el que genera `Set-Content`/`Out-File`
    a PowerShell 5.1, l'shell d'aquesta màquina—, que porta un NUL per cada caràcter ASCII, i
    (b) qualsevol dump comprimit. Els dos donaven `net = True` amb la clau sencera a dins.
    """
    descomprimit = _descomprimeix(dades, limit)
    if descomprimit is not None:
        dades = descomprimit

    if b"\x00" not in dades[:8192]:
        return dades.decode("utf-8", errors="replace"), ""

    if dades[:2] in (b"\xff\xfe", b"\xfe\xff"):
        try:
            return dades.decode("utf-16", errors="replace"), "utf-16 (BOM)"
        except (UnicodeDecodeError, LookupError):
            pass

    # UTF-16 sense BOM: els NUL cauen sistemàticament a les posicions senars (LE) o parells (BE).
    mostra = dades[:8192]
    meitat = max(1, len(mostra) // 2)
    for codec, nuls in (
        ("utf-16-le", mostra[1::2].count(0)),
        ("utf-16-be", mostra[0::2].count(0)),
    ):
        if nuls >= meitat * 0.3:
            return dades.decode(codec, errors="replace"), codec

    return None, "binari"


def _es_binari(dades: bytes) -> bool:
    """Compat: cert si els bytes no són auditables com a text (ni UTF-8, ni UTF-16, ni arxiu)."""
    text, _ = _a_text(dades, limit=len(dades) + 1)
    return text is None


def _ruta_de_risc(ruta: str) -> bool:
    r = ruta.lower()
    return any(p in r for p in _PATRONS_RUTA_RISC)


def _troballa_no_auditada(
    zona: str,
    ruta: str,
    *,
    motiu: str,
    mida: int = -1,
    blob: str = "",
    rutes: list[str] | None = None,
) -> Troballa:
    """Troballa que diu "això NO s'ha mirat".

    És deliberadament una troballa i no una nota: un artefacte que se salta el límit de mida és
    precisament el que concentra la PII massiva (un `pg_dump` de 4 xifres d'alumnes). Que el
    gate digui NET perquè el fitxer era massa gros és el pitjor fals negatiu possible.
    El fingerprint es deriva de la ruta i la mida (cap material sensible: no s'ha llegit res).
    """
    detall = f"motiu={motiu}"
    if mida >= 0:
        detall += f"; mida={mida}"
    return Troballa(
        zona=zona,
        tipus="no_auditat_per_mida" if motiu == "supera --max-mida-mb" else "no_auditat",
        ruta=ruta,
        linia=0,
        fingerprint=_fingerprint(f"no_auditat|{ruta}|{mida}"),
        detall=detall,
        classificacio=CLAS_NO_AUDITAT,
        blob=blob,
        rutes=rutes or [ruta],
    )


# ─────────────────────────── zona ARBRE (working tree) ───────────────────────────


def _fitxers_arbre(repo: str, *, nomes_versionats: bool = False):
    """Genera (ruta_absoluta, ruta_relativa) del working tree, inclosos els texts de `.git`."""
    if nomes_versionats:
        codi, dades = _git(repo, ["ls-files", "-z"])
        if codi != 0:
            raise RuntimeError("No es pot inventariar l'arbre versionat.")
        for rel in dades.decode("utf-8", "replace").split("\0"):
            if rel:
                yield os.path.join(repo, rel), rel
        return
    for arrel, dirs, noms in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in _DIRS_OMESOS]
        for nom in noms:
            abs_ruta = os.path.join(arrel, nom)
            yield abs_ruta, os.path.relpath(abs_ruta, repo).replace(os.sep, "/")
    # `.git` no es recorre sencer (objectes zlib), però els seus fitxers de text sí: un
    # `url = https://usuari:token@github.com/...` a `.git/config` és una credencial en clar.
    for nom in _FITXERS_GIT:
        abs_ruta = os.path.join(repo, ".git", nom)
        if os.path.isfile(abs_ruta):
            yield abs_ruta, f".git/{nom}"


def escaneja_arbre(repo: str, *, mida_max: int, estricte: bool = False, nomes_versionats: bool = False) -> tuple[list[Troballa], dict]:
    """Escaneja el working tree.

    NO es respecta `.gitignore` a propòsit: un `.env` ignorat amb credencials de producció és
    precisament el que volem veure. Ignorar-lo perquè git l'ignora seria confondre "no
    versionat" amb "no exposat" (una còpia del directori, un `docker build` amb el context
    sencer o un backup se l'emporten igual).
    """
    troballes: list[Troballa] = []
    fitxers = 0
    enllacos = 0
    per_mida: list[str] = []
    binaris: list[str] = []
    illegibles: list[str] = []
    for abs_ruta, rel in _fitxers_arbre(repo, nomes_versionats=nomes_versionats):
        try:
            if os.path.islink(abs_ruta):
                enllacos += 1
                continue
            mida = os.path.getsize(abs_ruta)
            if mida > mida_max:
                per_mida.append(rel)
                troballes.append(
                    _troballa_no_auditada("arbre", rel, motiu="supera --max-mida-mb", mida=mida)
                )
                continue
            with open(abs_ruta, "rb") as fh:
                dades = fh.read()
        except OSError:
            # Fitxer bloquejat, permisos o cursa amb un altre procés. Si la ruta és de risc no
            # es pot dissimular amb un comptador: surt com a troballa.
            illegibles.append(rel)
            if _ruta_de_risc(rel):
                troballes.append(_troballa_no_auditada("arbre", rel, motiu="il·legible"))
            continue
        text, motiu = _a_text(dades, limit=mida_max)
        if text is None:
            binaris.append(rel)
            continue
        fitxers += 1
        troballes.extend(_escaneja_text(text, rel, "arbre", estricte=estricte))
    return troballes, {
        "fitxers_escanejats": fitxers,
        "fitxers_omesos": len(per_mida) + len(binaris) + len(illegibles) + enllacos,
        "fitxers_omesos_per_mida": per_mida,
        "fitxers_omesos_binaris": binaris,
        "fitxers_omesos_illegibles": illegibles,
        "enllacos_simbolics": enllacos,
    }


# ─────────────────────────── zona HISTORIAL (objectes git) ───────────────────────────


def _git(repo: str, args: list[str], *, binari: bool = False) -> tuple[int, bytes]:
    """Executa git sense fer petar el procés: retorna (returncode, stdout).

    127 = `git` no s'ha pogut executar (absent del PATH). El cridador HA de distingir-ho de
    "git ha respost que no": una imatge de CI slim sense git no pot convertir el gate en un
    no-op verd.
    """
    try:
        p = subprocess.run(
            ["git", "-C", repo, *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except (OSError, ValueError):
        return 127, b""
    return p.returncode, p.stdout if binari else p.stdout


def estat_git(repo: str) -> dict:
    """Radiografia del repositori: disponible, bare, shallow, parcial, versió.

    Es detecta amb `rev-parse --git-dir` i NO amb `--is-inside-work-tree`: en un repo BARE
    (el que produeix `git clone --mirror`, que és exactament el que el runbook mana clonar per
    verificar) `--is-inside-work-tree` diu `false` i la versió anterior degradava a `--arbre`,
    escanejava el directori `.git` com si fos un working tree —objectes zlib, tots "binaris"—
    i imprimia `RESULTAT: NET`. El criteri de sortida de la Fase 0 era una màquina de falsos
    negatius.
    """
    codi_v, sortida_v = _git(repo, ["--version"])
    disponible = codi_v == 0
    versio = sortida_v.decode("utf-8", errors="replace").strip() if disponible else ""

    codi, sortida = _git(repo, ["rev-parse", "--git-dir"])
    es_repo = disponible and codi == 0
    git_dir = sortida.decode("utf-8", errors="replace").strip() if es_repo else ""

    def _flag(nom: str) -> bool:
        c, s = _git(repo, ["rev-parse", nom])
        return c == 0 and s.strip() == b"true"

    es_bare = es_repo and _flag("--is-bare-repository")
    es_shallow = es_repo and _flag("--is-shallow-repository")

    es_parcial = False
    if es_repo:
        # Clon parcial (`--filter=blob:none`): els blobs no hi són, només les promeses.
        c, s = _git(repo, ["config", "--get-regexp", r"^remote\..*\.partialclonefilter$"])
        es_parcial = c == 0 and bool(s.strip())
        if not es_parcial:
            c, s = _git(repo, ["rev-parse", "--git-path", "objects"])
            if c == 0:
                dir_obj = s.decode("utf-8", errors="replace").strip()
                if not os.path.isabs(dir_obj):
                    dir_obj = os.path.join(repo, dir_obj)
                es_parcial = bool(glob.glob(os.path.join(dir_obj, "pack", "*.promisor")))

    return {
        "git_disponible": disponible,
        "git_versio": versio,
        "es_repo": es_repo,
        "git_dir": git_dir,
        "es_bare": es_bare,
        "es_shallow": es_shallow,
        "es_parcial": es_parcial,
    }


def es_repo_git(repo: str) -> bool:
    """Cert si `repo` és un repositori git (bare inclòs)."""
    return estat_git(repo)["es_repo"]


def _rutes_per_blob(repo: str) -> tuple[dict[str, list[str]], bool]:
    """Mapa blob→ruta via `git rev-list --objects --all`.

    ATENCIÓ: `rev-list --objects` llista cada objecte UNA sola vegada, amb la primera ruta que
    troba. Si el mateix contingut viu a `a.txt` i a `backups/dump.sql`, git en dedupica el blob
    i només en surt una ruta. Per això aquest mapa és només la base i s'enriqueix amb
    `_index_historial` (que recorre `git log --raw`, on hi surten TOTES les parelles blob↔ruta).

    Retorna també si l'ordre ha reeixit: "cap ruta" i "no s'han pogut llistar les rutes" són
    coses diferents i confondre-les és exactament el que feia sortir informes nets.
    """
    codi, sortida = _git(repo, ["rev-list", "--objects", "--all"])
    mapa: dict[str, list[str]] = {}
    if codi != 0:
        return mapa, False
    for linia in sortida.decode("utf-8", errors="replace").splitlines():
        sha, _, ruta = linia.partition(" ")
        if not ruta:
            continue
        mapa.setdefault(sha, [])
        if ruta not in mapa[sha]:
            mapa[sha].append(ruta)
    return mapa, True


_RE_LINIA_RAW = re.compile(r"^:\d+ \d+ ([0-9a-f]{40,}) ([0-9a-f]{40,}) [A-Z]\d*\t(.+)$")


def _index_historial(repo: str) -> tuple[dict[str, list[str]], dict[str, list[str]], list[str]]:
    """Recorre l'historial UNA vegada i retorna (rutes_per_blob, commits_per_blob, errors).

    Es fa amb `git log --all --root --raw`, que emet una línia per cada parella (blob, ruta) de
    cada canvi. Dos motius:

    1. **Totes les rutes.** `rev-list --objects` en dona una i prou, i la via A de remediació
       (`git filter-repo --invert-paths --path …`) necessita la llista sencera: si el blob també
       ha viscut a una ruta que no hem enumerat, la purga el deixa viu.
    2. **Cost.** Abans es cridava `git log --all --find-object=<sha>` una vegada PER TROBALLA,
       és a dir un recorregut complet de l'historial per cada secret. Amb l'índex es fa un sol
       recorregut per a tot el repositori.
    """
    errors: list[str] = []
    rutes: dict[str, list[str]] = {}
    commits: dict[str, list[str]] = {}

    base, ok = _rutes_per_blob(repo)
    if not ok:
        errors.append(
            "`git rev-list --objects --all` ha fallat: no s'han pogut atribuir rutes als blobs."
        )
    rutes.update({sha: list(r) for sha, r in base.items()})

    codi, sortida = _git(
        repo,
        [
            "log",
            "--all",
            "--root",
            "--full-history",
            "--no-renames",
            "--raw",
            "--no-abbrev",
            "--format=%x01%H",
        ],
    )
    if codi != 0:
        errors.append(
            "`git log --all --raw` ha fallat: no s'han pogut recuperar totes les rutes ni els "
            "commits de cada blob."
        )
        return rutes, commits, errors

    commit_actual = ""
    for linia in sortida.decode("utf-8", errors="replace").splitlines():
        if linia.startswith("\x01"):
            commit_actual = linia[1:].strip()[:12]
            continue
        m = _RE_LINIA_RAW.match(linia)
        if not m:
            continue
        ruta = m.group(3).split("\t")[-1]
        for sha in (m.group(1), m.group(2)):
            if not sha.strip("0"):
                continue  # 000…0 = el blob no existia (alta) o ja no existeix (baixa)
            llista = rutes.setdefault(sha, [])
            if ruta not in llista:
                llista.append(ruta)
            if commit_actual:
                cs = commits.setdefault(sha, [])
                if commit_actual not in cs:
                    cs.append(commit_actual)
    return rutes, commits, errors


def _blobs_tots(repo: str, *, mida_max: int) -> tuple[list[str], list[tuple[str, int]], bool]:
    """Tots els blobs de la base d'objectes (inclosos els PENJANTS) que caben al límit.

    S'usa `--batch-all-objects` i no només els assolibles des de les branques: un blob
    unreachable (amend, reset, branca esborrada) encara es recupera amb `git cat-file` mentre
    no passi el `gc`, i per tant continua sent exposició real.

    Retorna (shas dins del límit, [(sha, mida) descartats per mida], ordre_ok).
    """
    codi, sortida = _git(
        repo,
        ["cat-file", "--batch-all-objects", "--batch-check=%(objectname) %(objecttype) %(objectsize)"],
    )
    blobs: list[str] = []
    omesos: list[tuple[str, int]] = []
    if codi != 0:
        return blobs, omesos, False
    for linia in sortida.decode("ascii", errors="replace").splitlines():
        parts = linia.split()
        if len(parts) != 3 or parts[1] != "blob":
            continue
        try:
            mida = int(parts[2])
        except ValueError:
            continue
        if mida <= mida_max:
            blobs.append(parts[0])
        else:
            omesos.append((parts[0], mida))
    return blobs, omesos, True


def _llegeix_blobs(repo: str, shas: list[str], mida_lot: int = 128):
    """Generador (sha, dades) llegint per lots amb `git cat-file --batch`.

    Es fa per lots petits i tancant stdin abans de llegir stdout: escriure ~5 KiB de SHAs cap
    tot als buffers del pipe, així que no hi pot haver bloqueig mutu amb git (que sí que
    passaria si escrivíssim desenes de milers de SHAs mentre ell omple stdout).
    """
    for i in range(0, len(shas), mida_lot):
        lot = shas[i : i + mida_lot]
        try:
            p = subprocess.run(
                ["git", "-C", repo, "cat-file", "--batch"],
                input=("\n".join(lot) + "\n").encode("ascii"),
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except (OSError, ValueError):
            continue
        buf = p.stdout
        pos = 0
        for _ in lot:
            fi = buf.find(b"\n", pos)
            if fi < 0:
                break
            capcalera = buf[pos:fi].decode("ascii", errors="replace").split()
            pos = fi + 1
            if len(capcalera) != 3:
                # "<obj> missing": no hi ha cos a saltar.
                continue
            try:
                mida = int(capcalera[2])
            except ValueError:
                break
            dades = buf[pos : pos + mida]
            pos += mida + 1  # el cos ve seguit d'un \n
            yield capcalera[0], dades


def _commits_del_blob(repo: str, sha: str, *, max_commits: int = 20) -> list[str]:
    """Commits (curts) que van introduir o eliminar aquest blob exacte.

    `--find-object` compara per SHA d'objecte, no per ruta ni per text: si el mateix secret
    s'ha mogut de fitxer, surt igualment. Llista buida = blob penjant (no el referencia cap
    commit assolible) i això és MÉS greu, no menys: no es pot "arreglar" reescrivint una
    branca, cal expirar el reflog i fer gc.
    """
    codi, sortida = _git(repo, ["log", "--all", "--format=%h", f"--find-object={sha}"])
    if codi != 0:
        return []
    return sortida.decode("ascii", errors="replace").split()[:max_commits]


_RUTA_PENJANT = "(objecte penjant, sense ruta)"


def escaneja_historial(repo: str, *, mida_max: int, estricte: bool = False) -> tuple[list[Troballa], dict, list[str]]:
    """Escaneja tots els blobs de l'historial (i els penjants).

    Retorna (troballes, mètriques, errors). `errors` no buit ⇒ l'auditoria NO és completa i el
    cridador ha de retornar un codi de sortida != 0 encara que no hi hagi cap troballa.
    """
    errors: list[str] = []

    codi, sortida = _git(repo, ["rev-list", "--all", "--count"])
    if codi != 0:
        errors.append("`git rev-list --all --count` ha fallat: no s'ha pogut comptar l'historial.")
    total_commits = int(sortida.strip() or b"0") if codi == 0 else 0

    mapa_rutes, mapa_commits, errs_index = _index_historial(repo)
    errors.extend(errs_index)

    shas, omesos_mida, blobs_ok = _blobs_tots(repo, mida_max=mida_max)
    if not blobs_ok:
        errors.append(
            "`git cat-file --batch-all-objects` ha fallat: la base d'objectes NO s'ha enumerat."
        )

    troballes: list[Troballa] = []
    # Els blobs massa grans no es llegeixen, però es reporten: són els candidats naturals a
    # contenir un dump sencer.
    for sha, mida in omesos_mida:
        rutes = mapa_rutes.get(sha) or []
        troballes.append(
            _troballa_no_auditada(
                "historial",
                rutes[0] if rutes else _RUTA_PENJANT,
                motiu="supera --max-mida-mb",
                mida=mida,
                blob=sha[:12],
                rutes=rutes,
            )
        )

    escanejats = 0
    binaris: list[str] = []
    for sha, dades in _llegeix_blobs(repo, shas):
        rutes = sorted(mapa_rutes.get(sha) or [])
        text, _motiu = _a_text(dades, limit=mida_max)
        if text is None:
            binaris.append(f"{sha[:12]} {rutes[0] if rutes else _RUTA_PENJANT}")
            continue
        escanejats += 1
        # Sense ruta assolible → `rutes=()` → cap detector es descarta "per ruta". És el cas del
        # blob penjant que deixa un `git commit --amend`, i és precisament on la PII de menors
        # quedava invisible: la ruta inventada "(objecte penjant…)" no contenia ni `.sql` ni
        # `backup`, així que el detector de dumps no s'aplicava MAI als penjants.
        ruta = rutes[0] if rutes else _RUTA_PENJANT
        commits_blob = mapa_commits.get(sha) or _commits_del_blob(repo, sha)
        for t in _escaneja_text(text, ruta, "historial", rutes=tuple(rutes), estricte=estricte):
            t.blob = sha[:12]
            t.commits = commits_blob[:20]
            troballes.append(t)

    return (
        troballes,
        {
            "commits_totals": total_commits,
            "blobs_candidats": len(shas),
            "blobs_escanejats": escanejats,
            "blobs_omesos_per_mida": [{"blob": s[:12], "mida": m} for s, m in omesos_mida],
            "blobs_omesos_binaris": binaris,
        },
        errors,
    )


# ─────────────────────────── llista blanca ───────────────────────────


@dataclass(frozen=True)
class RegleBlanca:
    """Una entrada de llista blanca, sempre amb àmbit.

    Silenciar per fingerprint *nu* era insuficient: n'hi havia prou que dos materials diferents
    compartissin fingerprint (cas del nom de taula) perquè una justificació escrita sobre un
    seed sintètic amagués el dump real de menors. Ara l'àmbit (tipus, ruta) és opcional però
    disponible, i les troballes de PII de menors exigeixen una regla `pii` amb tiquet.
    """

    fingerprint: str
    tipus: str | None = None
    ruta: str | None = None
    tiquet: str | None = None
    pii: bool = False


def analitza_regles(entrades: Iterable[str], *, pii: bool = False) -> tuple[RegleBlanca, ...]:
    """Parseja `FP[:TIPUS[:RUTA]]` (i `…=TIQUET`, obligatori per a `--permet-pii`)."""
    regles: list[RegleBlanca] = []
    for entrada in entrades:
        for tros in entrada.split(","):
            tros = tros.strip()
            if not tros:
                continue
            ambit, _, tiquet = tros.partition("=")
            parts = ambit.split(":")
            fp = parts[0].strip().lower()
            if not fp:
                continue
            if pii and not tiquet.strip():
                raise ValueError(
                    f"--permet-pii exigeix referència de tiquet: {fp}=TIQUET (rebut {tros!r})."
                )
            regles.append(
                RegleBlanca(
                    fingerprint=fp,
                    tipus=(parts[1].strip() or None) if len(parts) > 1 else None,
                    ruta=(parts[2].strip() or None) if len(parts) > 2 else None,
                    tiquet=tiquet.strip() or None,
                    pii=pii,
                )
            )
    return tuple(regles)


def _silenciada(t: Troballa, regles: Iterable[RegleBlanca]) -> bool:
    """Cert si una regla de llista blanca cobreix aquesta troballa exacta."""
    es_pii = t.classificacio == CLAS_PII_MENORS
    for r in regles:
        if r.fingerprint != t.fingerprint:
            continue
        # Una troballa de PII de menors NOMÉS la pot silenciar una regla `--permet-pii` (amb
        # tiquet); i una regla de PII no serveix per a res més.
        if r.pii != es_pii:
            continue
        if r.tipus and r.tipus != t.tipus:
            continue
        if r.ruta and r.ruta.lower() not in t.ruta.lower():
            continue
        return True
    return False


# ─────────────────────────── informe ───────────────────────────


def construeix_informe(
    repo: str,
    *,
    fer_arbre: bool,
    fer_historial: bool,
    mida_max: int,
    permesos: Iterable[str] = (),
    permesos_pii: Iterable[str] = (),
    estricte: bool = False,
    nomes_versionats: bool = False,
) -> dict:
    """Executa els modes demanats i retorna l'informe complet (ja sanejat).

    Invariant del gate: **un mode demanat que no s'ha pogut executar és un error**, no una
    degradació silenciosa. `auditoria_completa=False` ⇒ `net=False` ⇒ `codi_sortida=2`. Sense
    això, `git clone --mirror` (bare), `git clone --depth 1` (el defecte d'`actions/checkout`),
    un clon parcial o una imatge de CI sense `git` donaven `exit 0` amb el repo ple de claus.
    """
    repo = os.path.abspath(repo)
    git = estat_git(repo)
    avisos: list[str] = []
    errors: list[str] = []

    arbre_demanat, historial_demanat = fer_arbre, fer_historial

    if historial_demanat and not git["git_disponible"]:
        errors.append(
            "`git` no és disponible al PATH: s'ha demanat --historial i NO s'ha pogut auditar."
        )
        fer_historial = False
    elif historial_demanat and not git["es_repo"]:
        errors.append(
            "El directori no és un repositori git: s'ha demanat --historial i NO s'ha pogut "
            "auditar. L'auditoria de l'arbre NO substitueix la de l'historial."
        )
        fer_historial = False

    if git["es_bare"] and fer_arbre:
        # Un bare/mirror no té working tree; escanejar-ne el directori seria llegir objectes
        # zlib i comptar-los com a "binaris omesos". Es desactiva i s'avisa.
        avisos.append(
            "Repositori BARE (clon --mirror): no hi ha working tree, el mode --arbre no s'hi "
            "aplica. Només s'audita l'historial."
        )
        fer_arbre = False

    if fer_historial and git["es_shallow"]:
        errors.append(
            "Clon SHALLOW (`--depth`): la base d'objectes només conté una part de l'historial. "
            "Torna a clonar sense `--depth` (a CI: `actions/checkout` amb `fetch-depth: 0`)."
        )
    if fer_historial and git["es_parcial"]:
        errors.append(
            "Clon PARCIAL (`--filter=blob:none`): falten blobs locals. Torna a clonar sense filtre."
        )

    if not fer_arbre and not fer_historial:
        errors.append("No s'ha pogut auditar cap zona: l'informe no prova res.")
        if git["es_bare"] and arbre_demanat and not historial_demanat:
            errors.append(
                "S'ha demanat només --arbre sobre un repositori BARE: usa --historial."
            )

    troballes: list[Troballa] = []
    metriques: dict = {}
    if fer_arbre:
        t, m = escaneja_arbre(repo, mida_max=mida_max, estricte=estricte, nomes_versionats=nomes_versionats)
        troballes.extend(t)
        metriques["arbre"] = m
    if fer_historial:
        t, m, errs = escaneja_historial(repo, mida_max=mida_max, estricte=estricte)
        troballes.extend(t)
        metriques["historial"] = m
        errors.extend(errs)

    regles = analitza_regles(permesos) + analitza_regles(permesos_pii, pii=True)
    ignorades = sum(1 for t in troballes if _silenciada(t, regles))
    troballes = [t for t in troballes if not _silenciada(t, regles)]

    # ── Severitat (el que decideix si el gate bloqueja) ───────────────────────
    # `git ls-files` un sol cop: saber si una ruta de l'ARBRE està VERSIONADA és el que
    # separa «secret al lloc correcte» (.env gitignored) de «secret exposat a qui cloni».
    versionats: set[str] = set()
    # Només si `git ls-files` respon podem separar «secret al lloc correcte» de «secret
    # exposat». Si falla o no és repo, `pot_determinar_versionat` queda fals i tot bloqueja.
    pot_determinar_versionat = False
    if git["es_repo"]:
        codi, sortida = _git(repo, ["ls-files", "-z"])
        if codi == 0:
            versionats = {r for r in sortida.decode("utf-8", "replace").split("\0") if r}
            pot_determinar_versionat = True
    for t in troballes:
        t.severitat = severitat_de(
            t.tipus, t.classificacio, t.ruta, t.zona,
            versionat=(t.ruta in versionats),
            placeholder=t.sembla_plantilla,
            pot_determinar_versionat=pot_determinar_versionat,
            material_fort=t.material_fort, estricte=estricte,
        )

    per_tipus: dict[str, int] = {}
    per_zona: dict[str, int] = {}
    per_severitat: dict[str, int] = {}
    for t in troballes:
        per_tipus[t.tipus] = per_tipus.get(t.tipus, 0) + 1
        per_zona[t.zona] = per_zona.get(t.zona, 0) + 1
        per_severitat[t.severitat] = per_severitat.get(t.severitat, 0) + 1
    bloquejants = per_severitat.get(SEV_BLOQUEJANT, 0)

    # Bloquejants primer: qui llegeix l'informe ha de veure a dalt el que atura la Fase 0.
    _ordre_sev = {SEV_BLOQUEJANT: 0, SEV_AVIS: 1, SEV_INFO: 2}
    troballes.sort(key=lambda t: (_ordre_sev.get(t.severitat, 0), t.zona, t.tipus, t.ruta, t.linia))
    modes = [m for m, actiu in (("arbre", fer_arbre), ("historial", fer_historial)) if actiu]
    auditoria_completa = not errors
    # NET = cap BLOQUEJANT (els avisos i els informatius no aturen el desplegament). Aquesta
    # és la diferència entre un gate que es pot tancar i un que crida el llop 69 vegades.
    net = auditoria_completa and not bloquejants
    return {
        "repo": repo,
        "generat_el": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "es_repo_git": git["es_repo"],
        "git_disponible": git["git_disponible"],
        "git_versio": git["git_versio"],
        "es_bare": git["es_bare"],
        "es_shallow": git["es_shallow"],
        "es_parcial": git["es_parcial"],
        "modes": modes,
        "modes_demanats": [
            m for m, actiu in (("arbre", arbre_demanat), ("historial", historial_demanat)) if actiu
        ],
        "avisos": avisos,
        "errors": errors,
        "auditoria_completa": auditoria_completa,
        "metriques": metriques,
        "patrons_coberts": sorted({d.tipus for d in DETECTORS}),
        "troballes": [t.dict() for t in troballes],
        "resum": {
            "total": len(troballes),
            "bloquejants": bloquejants,
            "ignorades_per_llista_blanca": ignorades,
            "fingerprints_permesos": sorted({r.fingerprint for r in regles}),
            "per_tipus": dict(sorted(per_tipus.items())),
            "per_zona": dict(sorted(per_zona.items())),
            "per_severitat": dict(sorted(per_severitat.items())),
        },
        "net": net,
        # 2 pesa més que 1: "no ho sé" és pitjor que "sé que hi ha això".
        # Només bloquegen els BLOQUEJANTS: un `.env` gitignored amb secrets reals o una
        # variable anomenada `token` no poden impedir un desplegament.
        "codi_sortida": 2 if not auditoria_completa else (1 if bloquejants else 0),
    }


def _llista_curta(valors: list, maxim: int = 8) -> str:
    mostrats = [str(v) for v in valors[:maxim]]
    if len(valors) > maxim:
        mostrats.append(f"…(+{len(valors) - maxim})")
    return ", ".join(mostrats)


def formata_text(informe: dict) -> str:
    """Resum llegible. Cap línia d'aquesta sortida conté material sensible."""
    linies = [
        "Auditoria de secrets/PII (READ-ONLY, sense revelar el contingut)",
        f"Repo:   {informe['repo']}",
        f"Modes:  {', '.join(informe['modes']) or '(cap)'}"
        f"  (demanats: {', '.join(informe['modes_demanats']) or 'tots'})",
        f"Git:    {informe['git_versio'] or 'NO DISPONIBLE'}"
        f"  bare={informe['es_bare']} shallow={informe['es_shallow']} parcial={informe['es_parcial']}",
        f"Data:   {informe['generat_el']}",
    ]
    for avis in informe["avisos"]:
        linies.append(f"AVÍS:   {avis}")
    for err in informe["errors"]:
        linies.append(f"ERROR:  {err}")

    m = informe["metriques"]
    if "arbre" in m:
        a = m["arbre"]
        linies.append(
            f"Arbre:      {a['fitxers_escanejats']} fitxers escanejats, "
            f"{a['fitxers_omesos']} omesos"
        )
        if a["fitxers_omesos_per_mida"]:
            linies.append(
                f"  · omesos per mida ({len(a['fitxers_omesos_per_mida'])}): "
                f"{_llista_curta(a['fitxers_omesos_per_mida'])}"
            )
        if a["fitxers_omesos_binaris"]:
            linies.append(
                f"  · omesos per binari ({len(a['fitxers_omesos_binaris'])}): "
                f"{_llista_curta(a['fitxers_omesos_binaris'])}"
            )
        if a["fitxers_omesos_illegibles"]:
            linies.append(
                f"  · il·legibles ({len(a['fitxers_omesos_illegibles'])}): "
                f"{_llista_curta(a['fitxers_omesos_illegibles'])}"
            )
    if "historial" in m:
        h = m["historial"]
        linies.append(
            f"Historial:  {h['commits_totals']} commits, {h['blobs_escanejats']} blobs de text "
            f"escanejats (de {h['blobs_candidats']} candidats)"
        )
        if h["blobs_omesos_per_mida"]:
            etiquetes = ["{}({}B)".format(b["blob"], b["mida"]) for b in h["blobs_omesos_per_mida"]]
            linies.append(
                f"  · blobs omesos per mida ({len(etiquetes)}): {_llista_curta(etiquetes)}"
            )
        if h["blobs_omesos_binaris"]:
            linies.append(
                f"  · blobs omesos per binari ({len(h['blobs_omesos_binaris'])}): "
                f"{_llista_curta(h['blobs_omesos_binaris'])}"
            )

    if informe["resum"]["ignorades_per_llista_blanca"]:
        linies.append(
            f"Permeses:   {informe['resum']['ignorades_per_llista_blanca']} troballes silenciades "
            f"per llista blanca (verificades a mà)"
        )

    linies.append("")
    resum = informe["resum"]
    if resum["total"] == 0:
        if informe["auditoria_completa"]:
            linies.append(
                "RESULTAT: NET — cap troballa DELS PATRONS COBERTS "
                f"({len(informe['patrons_coberts'])}: {', '.join(informe['patrons_coberts'])}). "
                "Criteri de sortida de la Fase 0 satisfet."
            )
        else:
            linies.append(
                "RESULTAT: INDETERMINAT — cap troballa, però l'auditoria NO s'ha pogut completar "
                "(vegeu ERROR més amunt). La Fase 0 NO es pot tancar amb aquest informe."
            )
        return "\n".join(linies)

    bloq = resum.get("bloquejants", resum["total"])
    encap = "TROBALLES" if informe["auditoria_completa"] else "TROBALLES + AUDITORIA INCOMPLETA"
    if bloq:
        linies.append(
            f"RESULTAT: {bloq} BLOQUEJANTS de {resum['total']} {encap} — la Fase 0 NO es pot tancar."
        )
    else:
        linies.append(
            f"RESULTAT: 0 BLOQUEJANTS de {resum['total']} {encap} — criteri de sortida SATISFET. "
            "La resta són avisos (baixa confiança o material NO versionat, p. ex. un `.env` "
            "gitignored: és on han de viure els secrets) i informatius (plantilles, fixtures)."
        )
    linies.append("Severitat:  " + ", ".join(f"{k}={v}" for k, v in resum.get("per_severitat", {}).items()))
    linies.append("Per tipus:  " + ", ".join(f"{k}={v}" for k, v in resum["per_tipus"].items()))
    linies.append("Per zona:   " + ", ".join(f"{k}={v}" for k, v in resum["per_zona"].items()))
    linies.append("")
    linies.append("  zona       tipus                          ruta:línia   fp / blob / commits")
    for t in informe["troballes"]:
        commits = ",".join(t["commits"][:6]) or ("penjant" if t["zona"] == "historial" else "-")
        extra = f" [{t['detall']}]" if t["detall"] else ""
        rep = f" x{t['ocurrencies']}" if t["ocurrencies"] > 1 else ""
        blob = f" blob={t['blob']}" if t["blob"] else ""
        linies.append(
            f"  {t['zona']:<10} {t['tipus']:<30} {t['ruta']}:{t['linia']}{rep}{extra}"
            f"   fp={t['fingerprint']}{blob} commits={commits}"
        )
        if t["rutes_alternatives"]:
            # La via A de remediació (`git filter-repo --path …`) necessita TOTES les rutes:
            # amb un comptador la llista es construeix incompleta i la purga deixa el secret viu.
            linies.append(f"      rutes: {_llista_curta(t['rutes'], 12)}")
    linies.append("")
    linies.append(
        "Remediació: docs/RUNBOOK_SEGURETAT_INS_BITACOLA.md — ROTAR primer, purgar l'historial "
        "després, i tornar a executar aquest escàner fins a exit code 0."
    )
    return "\n".join(linies)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Auditor read-only de secrets i PII al working tree i a l'historial de git. "
            "Mai imprimeix el material sensible: només ruta, línia, commit, tipus i fingerprint."
        )
    )
    ap.add_argument("--repo", default=_ARREL_DEFECTE, help="Ruta del repositori a auditar.")
    ap.add_argument("--arbre", action="store_true", help="Només el working tree.")
    ap.add_argument("--historial", action="store_true", help="Només l'historial de git.")
    ap.add_argument("--informe", help="Ruta del JSON de sortida.")
    ap.add_argument("--json", action="store_true", help="Treu el JSON per stdout.")
    ap.add_argument(
        "--permet-fp",
        action="append",
        default=[],
        metavar="FP[:TIPUS[:RUTA]]",
        help=(
            "Fingerprint ja verificat a mà com a benigne (dummy, fixture de test). Repetible o "
            "separat per comes; es pot acotar per tipus i per ruta. Mai silencia una troballa "
            "de PII de menors: per a això cal --permet-pii."
        ),
    )
    ap.add_argument(
        "--permet-pii",
        action="append",
        default=[],
        metavar="FP[:TIPUS[:RUTA]]=TIQUET",
        help=(
            "Silencia una troballa de classificació `pii_menors`. Exigeix referència de tiquet "
            "escrita: amagar dades de menors no pot ser una decisió sense rastre."
        ),
    )
    ap.add_argument(
        "--max-mida-mb",
        type=float,
        default=_MIDA_MAX_MB_DEFECTE,
        help=(
            f"Mida màxima per fitxer/blob a escanejar (per defecte {_MIDA_MAX_MB_DEFECTE} MB). "
            "El que se salti el límit surt com a troballa `no_auditat_per_mida`, mai com a NET."
        ),
    )
    ap.add_argument("--estricte", action="store_true", help="Cap excepció implícita per tests, exemples o marcadors dins d'una credencial.")
    ap.add_argument("--nomes-versionats", action="store_true", help="Arbre només de git ls-files; no llegeix configuració local ignorada.")
    args = ap.parse_args(argv)

    if not os.path.isdir(args.repo):
        print(f"ERROR: no existeix el directori {args.repo!r}.", file=sys.stderr)
        return 2

    # Sense flags → tots dos modes. És el comportament segur: qui no tria, ho vol tot mirat.
    fer_arbre = args.arbre or not (args.arbre or args.historial)
    fer_historial = args.historial or not (args.arbre or args.historial)

    try:
        informe = construeix_informe(
            args.repo,
            fer_arbre=fer_arbre,
            fer_historial=fer_historial,
            mida_max=int(args.max_mida_mb * 1024 * 1024),
            permesos=args.permet_fp,
            permesos_pii=args.permet_pii, estricte=args.estricte, nomes_versionats=args.nomes_versionats,
        )
    except ValueError as exc:
        print(f"ERROR d'ús: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 — mai un traceback: això corre com a gate de CI
        print(f"ERROR d'execució de l'auditor: {type(exc).__name__}", file=sys.stderr)
        return 2

    if args.informe:
        try:
            directori = os.path.dirname(os.path.abspath(args.informe))
            if directori:
                os.makedirs(directori, exist_ok=True)
            with open(args.informe, "w", encoding="utf-8") as fh:
                json.dump(informe, fh, ensure_ascii=False, indent=2)
        except OSError as exc:
            print(f"ERROR: no s'ha pogut escriure l'informe: {exc}", file=sys.stderr)
            return 2

    if args.json:
        print(json.dumps(informe, ensure_ascii=False, indent=2))
    else:
        print(formata_text(informe))

    # 0 net · 1 troballes · 2 auditoria incompleta. Així serveix de gate de CI i de criteri de
    # sortida de la Fase 0 sense que ningú hagi d'interpretar el text.
    return int(informe["codi_sortida"])


if __name__ == "__main__":
    raise SystemExit(main())
