"""Originals: dry-run per defecte, esquema additiu, xifrat/rollback transaccionals.

No usa el DSN de l'app automàticament. Cal --env-file explícit o
PRIVACY_MIGRATION_DATABASE_URL; mai passar secrets a argv ni imprimir-los.
"""
from __future__ import annotations

import argparse
import json
import os
from types import SimpleNamespace

from sqlalchemy import MetaData, Table, and_, create_engine, func, inspect, select, text, update

from app.core import documents_crypto
from app.core.config import get_settings


def ensure_schema(conn, *, apply: bool = False) -> dict:
    inspector = inspect(conn)
    if not inspector.has_table("document_originals"):
        raise ValueError("Falta la taula d'originals.")
    missing = "contingut_format" not in {c["name"] for c in inspector.get_columns("document_originals")}
    if missing and apply:
        conn.execute(text("ALTER TABLE document_originals ADD COLUMN contingut_format "
                          "VARCHAR(32) NOT NULL DEFAULT 'plain'"))
    return {"schema_pending": missing, "schema_changed": bool(missing and apply)}


def migrate(conn, *, tenant: str, apply: bool = False, rollback: bool = False,
            scope: str = "sensitive", max_rows: int = 100, max_bytes: int = 256 * 1024 * 1024) -> dict:
    if not tenant or scope not in {"sensitive", "all"} or not 1 <= max_rows <= 1000:
        raise ValueError("Tenant, abast o límit no vàlid.")
    schema = ensure_schema(conn)
    if schema["schema_pending"]:
        return {**schema, "mode": "dry-run", "action_required": "schema-only"}
    metadata = MetaData()
    originals = Table("document_originals", metadata, autoload_with=conn)
    documents = Table("documents", metadata, autoload_with=conn)
    join = originals.outerjoin(documents, and_(
        documents.c.doc_id == originals.c.doc_id,
        documents.c.institucio_id == originals.c.institucio_id))
    conditions = [originals.c.institucio_id == tenant]
    if scope == "sensitive":
        conditions.append(documents.c.sensibilitat == "sensible")
    candidates = select(originals).select_from(join).where(*conditions).order_by(originals.c.doc_id)
    total = int(conn.scalar(select(func.count()).select_from(join).where(*conditions)) or 0)
    if total > max_rows:
        raise ValueError("El lot supera el límit explícit; segmentar/validar la política abans d'executar.")
    total_bytes = int(conn.scalar(select(func.sum(func.length(originals.c.contingut)))
                                 .select_from(join).where(*conditions)) or 0)
    if not 1 <= max_bytes <= 512 * 1024 * 1024 or total_bytes > max_bytes:
        raise ValueError("El lot supera el pressupost de memòria explícit.")
    changed = checked = plain = encrypted = 0
    # PostgreSQL bloqueja aquestes files; UPDATE també comprova bytes/format per detectar canvis.
    for row in conn.execute(candidates.with_for_update(of=originals)).mappings():
        original = SimpleNamespace(**row)
        if original.contingut_format not in {"plain", documents_crypto.FORMAT}:
            raise ValueError("Format desconegut: cap canvi no es confirma.")
        content = documents_crypto.reveal(original, tenant, original.doc_id, migration=True)
        checked += 1
        plain += original.contingut_format == "plain"
        encrypted += original.contingut_format == documents_crypto.FORMAT
        if rollback:
            protected, new_format = content, "plain"
        else:
            if original.contingut_format == documents_crypto.FORMAT:
                continue
            protected, new_format = documents_crypto.protect(content, tenant, original.doc_id, required=True)
            verification = SimpleNamespace(institucio_id=tenant, doc_id=original.doc_id,
                                           contingut=protected, contingut_format=new_format)
            if documents_crypto.reveal(verification, tenant, original.doc_id, migration=True) != content:
                raise ValueError("Verificació de migració fallida.")
        if new_format == original.contingut_format:
            continue
        if apply:
            result = conn.execute(update(originals).where(
                originals.c.doc_id == original.doc_id, originals.c.institucio_id == tenant,
                originals.c.contingut_format == original.contingut_format,
                originals.c.contingut == original.contingut,
            ).values(contingut=protected, contingut_format=new_format))
            if result.rowcount != 1:
                raise ValueError("Canvi concurrent; cal repetir amb els serveis en manteniment.")
        changed += 1
    return {"mode": "apply" if apply else "dry-run", "direction": "rollback" if rollback else "encrypt",
            "scope": scope, "candidates": total, "checked": checked, "plain": plain,
            "encrypted": encrypted, "would_change": changed, "changed": changed if apply else 0}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file")
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--scope", choices=("sensitive", "all"), default="sensitive")
    parser.add_argument("--include-all", action="store_true", help="Inclou originals de qualsevol classificació.")
    parser.add_argument("--max-rows", type=int, default=100)
    parser.add_argument("--max-bytes", type=int, default=256 * 1024 * 1024)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--rollback", action="store_true")
    parser.add_argument("--schema-only", action="store_true")
    parser.add_argument("--ack-backup-restored", action="store_true")
    args = parser.parse_args()
    if args.include_all:
        args.scope = "all"
    if args.apply and not args.ack_backup_restored:
        parser.error("--apply exigeix --ack-backup-restored (backup i restauració aïllada verificats).")
    if args.env_file:
        from dotenv import dotenv_values
        values = dotenv_values(args.env_file)
        if not values:
            parser.error("Fitxer d'entorn explícit buit/no disponible.")
        os.environ.update({k: v for k, v in values.items() if v is not None})
    dsn = os.environ.get("PRIVACY_MIGRATION_DATABASE_URL") or (
        os.environ.get("DATABASE_URL") if args.env_file else None)
    if not dsn:
        parser.error("Cal un fitxer d'entorn explícit o PRIVACY_MIGRATION_DATABASE_URL.")
    get_settings.cache_clear()
    engine = None
    try:
        engine = create_engine(dsn, echo=False)
        with engine.begin() as conn:
            result = ensure_schema(conn, apply=args.apply) if args.schema_only else migrate(
                conn, tenant=args.tenant, apply=args.apply, rollback=args.rollback,
                scope=args.scope, max_rows=args.max_rows, max_bytes=args.max_bytes)
        print(json.dumps(result, sort_keys=True))
        return 2 if args.apply and result.get("schema_pending") and not args.schema_only else 0
    except Exception as exc:
        # Les excepcions de driver poden incloure DSN/paramètres/bytes: només el tipus.
        print(json.dumps({"error_type": type(exc).__name__, "transaction": "rolled_back"}))
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
