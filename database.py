"""
Modulo de banco de dados SQLite para armazenamento de leads.
"""

import os
import re
import sqlite3
import json
from datetime import datetime
from typing import Optional

DEFAULT_DB_PATH = "leads.db"


EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _resolve_db_path() -> str:
    raw = str(os.getenv("DB_PATH", DEFAULT_DB_PATH) or "").strip()
    if not raw:
        return DEFAULT_DB_PATH

    # Railway Variables podem vir com aspas se coladas do .env.
    if (raw.startswith('"') and raw.endswith('"')) or (raw.startswith("'") and raw.endswith("'")):
        raw = raw[1:-1].strip()

    return raw or DEFAULT_DB_PATH


def _ensure_db_parent_dir(path: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def get_db():
    """Retorna uma conexao com o banco de dados."""
    db_path = _resolve_db_path()

    try:
        _ensure_db_parent_dir(db_path)
        conn = sqlite3.connect(db_path)
    except sqlite3.OperationalError as exc:
        print(f"Falha ao abrir DB_PATH='{db_path}': {exc}. Usando fallback '{DEFAULT_DB_PATH}'.")
        conn = sqlite3.connect(DEFAULT_DB_PATH)

    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Inicializa o banco de dados criando as tabelas necessarias."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT UNIQUE NOT NULL,
            empresa TEXT DEFAULT '',
            contato TEXT DEFAULT '',
            cnpj TEXT DEFAULT '',
            email TEXT DEFAULT '',
            telefone TEXT DEFAULT '',
            phone_normalized TEXT DEFAULT '',
            channel_id TEXT DEFAULT '',
            email_telefone TEXT DEFAULT '',
            segmento TEXT DEFAULT '',
            produtos_interesse TEXT DEFAULT '',
            volume_compra TEXT DEFAULT '',
            fornecedor_atual TEXT DEFAULT '',
            dores_necessidades TEXT DEFAULT '',
            decisores TEXT DEFAULT '',
            proximo_passo TEXT DEFAULT '',
            qualification_summary TEXT DEFAULT '',
            qualification_completed_at TIMESTAMP,
            status TEXT DEFAULT 'novo',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cursor.execute("PRAGMA table_info(leads)")
    existing_columns = {row[1] for row in cursor.fetchall()}
    if "email" not in existing_columns:
        cursor.execute("ALTER TABLE leads ADD COLUMN email TEXT DEFAULT ''")
    if "telefone" not in existing_columns:
        cursor.execute("ALTER TABLE leads ADD COLUMN telefone TEXT DEFAULT ''")
    if "phone_normalized" not in existing_columns:
        cursor.execute("ALTER TABLE leads ADD COLUMN phone_normalized TEXT DEFAULT ''")
    if "channel_id" not in existing_columns:
        cursor.execute("ALTER TABLE leads ADD COLUMN channel_id TEXT DEFAULT ''")
    if "email_telefone" not in existing_columns:
        cursor.execute("ALTER TABLE leads ADD COLUMN email_telefone TEXT DEFAULT ''")
    if "qualification_summary" not in existing_columns:
        cursor.execute("ALTER TABLE leads ADD COLUMN qualification_summary TEXT DEFAULT ''")
    if "qualification_completed_at" not in existing_columns:
        cursor.execute("ALTER TABLE leads ADD COLUMN qualification_completed_at TIMESTAMP")

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS lead_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            metadata TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_lead_messages_session_id
        ON lead_messages(session_id, created_at, id)
        """
    )

    _repair_lead_lookup_phones(cursor)

    conn.commit()
    conn.close()
    print("Banco de dados inicializado com sucesso.")


def _repair_lead_lookup_phones(cursor) -> int:
    """Restaura a chave de telefone do WhatsApp quando ela existe no session_id."""
    cursor.execute("SELECT id, session_id, phone_normalized FROM leads WHERE session_id LIKE 'lead:%'")
    repaired_count = 0
    for row in cursor.fetchall():
        session_phone = normalize_phone(str(row["session_id"] or "")[5:])
        if not session_phone:
            continue
        current_phone = normalize_phone(row["phone_normalized"])
        if current_phone == session_phone:
            continue
        cursor.execute(
            "UPDATE leads SET phone_normalized = ?, updated_at = ? WHERE id = ?",
            (session_phone, datetime.now().isoformat(), row["id"]),
        )
        repaired_count += 1
    if repaired_count:
        print(f"Telefones de lookup reparados: {repaired_count}")
    return repaired_count


def save_lead(session_id: str, lead_info: dict) -> bool:
    """Salva ou atualiza informacoes do lead."""
    conn = get_db()
    cursor = conn.cursor()

    try:
        explicit_phone_normalized = bool(str((lead_info or {}).get("phone_normalized", "")).strip())
        normalized = _normalize_contact_fields(lead_info)

        cursor.execute("SELECT * FROM leads WHERE session_id = ?", (session_id,))
        existing = cursor.fetchone()

        if existing:
            updates = []
            values = []

            field_mapping = {
                "empresa": "empresa",
                "contato": "contato",
                "cnpj": "cnpj",
                "email": "email",
                "telefone": "telefone",
                "phone_normalized": "phone_normalized",
                "channel_id": "channel_id",
                "email_telefone": "email_telefone",
                "segmento": "segmento",
                "produtos_interesse": "produtos_interesse",
                "volume_compra": "volume_compra",
                "fornecedor_atual": "fornecedor_atual",
                "dores_necessidades": "dores_necessidades",
                "decisores": "decisores",
                "proximo_passo": "proximo_passo",
            }

            existing_lookup_phone = normalize_phone(
                existing["phone_normalized"] if "phone_normalized" in existing.keys() else ""
            )
            for json_key, db_col in field_mapping.items():
                if (
                    json_key == "phone_normalized"
                    and existing_lookup_phone
                    and not explicit_phone_normalized
                ):
                    continue
                new_val = str(normalized.get(json_key, "")).strip()
                if new_val:
                    updates.append(f"{db_col} = ?")
                    values.append(new_val)

            if updates:
                updates.append("updated_at = ?")
                values.append(datetime.now().isoformat())
                values.append(session_id)

                query = f"UPDATE leads SET {', '.join(updates)} WHERE session_id = ?"
                cursor.execute(query, values)

                cursor.execute("SELECT * FROM leads WHERE session_id = ?", (session_id,))
                updated = cursor.fetchone()
                status = _resolve_next_status(updated, existing["status"])
                cursor.execute(
                    "UPDATE leads SET status = ? WHERE session_id = ?",
                    (status, session_id),
                )
        else:
            status = _resolve_next_status(normalized, str(normalized.get("status", "")).strip())
            now = datetime.now().isoformat()
            cursor.execute(
                """
                INSERT INTO leads (
                    session_id, empresa, contato, cnpj, email, telefone, phone_normalized, channel_id,
                    email_telefone, segmento,
                    produtos_interesse, volume_compra, fornecedor_atual,
                    dores_necessidades, decisores, proximo_passo, status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    normalized.get("empresa", ""),
                    normalized.get("contato", ""),
                    normalized.get("cnpj", ""),
                    normalized.get("email", ""),
                    normalized.get("telefone", ""),
                    normalized.get("phone_normalized", ""),
                    normalized.get("channel_id", ""),
                    normalized.get("email_telefone", ""),
                    normalized.get("segmento", ""),
                    normalized.get("produtos_interesse", ""),
                    normalized.get("volume_compra", ""),
                    normalized.get("fornecedor_atual", ""),
                    normalized.get("dores_necessidades", ""),
                    normalized.get("decisores", ""),
                    normalized.get("proximo_passo", ""),
                    status,
                    now,
                    now,
                ),
            )

        conn.commit()
        return True
    except Exception as exc:
        print(f"Erro ao salvar lead: {exc}")
        conn.rollback()
        return False
    finally:
        conn.close()


def create_active_lead(name: str, phone: str, channel_id: str) -> dict:
    """Cria ou reativa um lead iniciado por telefone."""
    normalized_phone = normalize_phone(phone)
    if not normalized_phone:
        raise ValueError("phone e obrigatorio")

    existing = get_lead_by_phone(phone)
    session_id = existing["session_id"] if existing else f"lead:{normalized_phone}"
    now = datetime.now().isoformat()

    conn = get_db()
    cursor = conn.cursor()
    try:
        if existing:
            cursor.execute(
                """
                UPDATE leads
                SET contato = ?, telefone = ?, phone_normalized = ?, channel_id = ?,
                    status = 'ACTIVE', updated_at = ?
                WHERE id = ?
                """,
                (name.strip(), phone.strip(), normalized_phone, channel_id.strip(), now, existing["id"]),
            )
        else:
            cursor.execute(
                """
                INSERT INTO leads (
                    session_id, contato, telefone, phone_normalized, channel_id,
                    status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, 'ACTIVE', ?, ?)
                """,
                (session_id, name.strip(), phone.strip(), normalized_phone, channel_id.strip(), now, now),
            )

        conn.commit()
        cursor.execute("SELECT * FROM leads WHERE session_id = ?", (session_id,))
        row = cursor.fetchone()
        return _serialize_lead(row)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_all_leads() -> list:
    """Retorna todos os leads cadastrados."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM leads ORDER BY updated_at DESC")
    rows = cursor.fetchall()

    leads = []
    for row in rows:
        leads.append(_serialize_lead(row))

    conn.close()
    return leads


def get_db_status() -> dict:
    """Retorna diagnostico seguro do banco em uso, sem expor segredos."""
    db_path = _resolve_db_path()
    resolved_path = os.path.abspath(db_path)
    status = {
        "db_path": db_path,
        "resolved_path": resolved_path,
        "exists": os.path.exists(db_path),
        "size_bytes": os.path.getsize(db_path) if os.path.exists(db_path) else 0,
        "cwd": os.getcwd(),
        "lead_count": None,
        "error": "",
    }

    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM leads")
        status["lead_count"] = cursor.fetchone()[0]
        conn.close()
    except Exception as exc:
        status["error"] = str(exc)

    return status


def get_lead_by_session(session_id: str) -> Optional[dict]:
    """Retorna um lead pelo session_id."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM leads WHERE session_id = ?", (session_id,))
    row = cursor.fetchone()

    conn.close()
    return _serialize_lead(row) if row else None


def append_conversation_message(
    session_id: str,
    role: str,
    content: str,
    metadata: Optional[dict] = None,
) -> bool:
    """Registra uma mensagem individual do historico da qualificacao."""
    role = str(role or "").strip()
    content = str(content or "").strip()
    if not session_id or role not in {"system", "user", "assistant"} or not content:
        return False

    conn = get_db()
    cursor = conn.cursor()

    try:
        now = datetime.now().isoformat()
        cursor.execute(
            """
            INSERT INTO lead_messages (session_id, role, content, metadata, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                session_id,
                role,
                content,
                json.dumps(metadata or {}, ensure_ascii=False),
                now,
            ),
        )
        cursor.execute(
            "UPDATE leads SET updated_at = ? WHERE session_id = ?",
            (now, session_id),
        )
        conn.commit()
        return True
    except Exception as exc:
        print(f"Erro ao salvar mensagem da conversa: {exc}")
        conn.rollback()
        return False
    finally:
        conn.close()


def get_conversation_messages(session_id: str) -> list[dict]:
    """Retorna o historico persistido da sessao."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, session_id, role, content, metadata, created_at
        FROM lead_messages
        WHERE session_id = ?
        ORDER BY created_at ASC, id ASC
        """,
        (session_id,),
    )
    rows = cursor.fetchall()
    conn.close()

    messages = []
    for row in rows:
        metadata = {}
        if row["metadata"]:
            try:
                metadata = json.loads(row["metadata"])
            except json.JSONDecodeError:
                metadata = {}
        messages.append(
            {
                "id": row["id"],
                "session_id": row["session_id"],
                "role": row["role"],
                "content": row["content"],
                "metadata": metadata,
                "created_at": row["created_at"],
            }
        )
    return messages


def save_qualification_summary(session_id: str, summary: str) -> bool:
    """Salva o resumo final da qualificacao no lead."""
    conn = get_db()
    cursor = conn.cursor()

    try:
        now = datetime.now().isoformat()
        cursor.execute(
            """
            UPDATE leads
            SET qualification_summary = ?,
                qualification_completed_at = ?,
                updated_at = ?
            WHERE session_id = ?
            """,
            (str(summary or "").strip(), now, now, session_id),
        )
        conn.commit()
        return cursor.rowcount > 0
    except Exception as exc:
        print(f"Erro ao salvar resumo da qualificacao: {exc}")
        conn.rollback()
        return False
    finally:
        conn.close()


def get_lead_by_phone(phone: str) -> Optional[dict]:
    """Retorna um lead pelo telefone, tolerando formatos diferentes."""
    normalized_phone = normalize_phone(phone)
    if not normalized_phone:
        return None

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM leads ORDER BY updated_at DESC")
    rows = cursor.fetchall()

    conn.close()

    for row in rows:
        row_phone_normalized = row["phone_normalized"] if "phone_normalized" in row.keys() else ""
        row_phone = row["telefone"] if "telefone" in row.keys() else ""
        if phones_match(row_phone_normalized, normalized_phone) or phones_match(row_phone, normalized_phone):
            return _serialize_lead(row)
    return None


def set_lead_status(session_id: str, status: str) -> bool:
    """Atualiza somente o status de um lead."""
    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute(
            "UPDATE leads SET status = ?, updated_at = ? WHERE session_id = ?",
            (status, datetime.now().isoformat(), session_id),
        )
        conn.commit()
        return cursor.rowcount > 0
    except Exception as exc:
        print(f"Erro ao atualizar status do lead: {exc}")
        conn.rollback()
        return False
    finally:
        conn.close()


def repair_finished_lead_statuses() -> dict:
    """Corrige leads que ja possuem desfecho final, mas permaneceram ACTIVE."""
    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT * FROM leads WHERE status = 'ACTIVE'")
        rows = cursor.fetchall()
        repaired = []
        for row in rows:
            lead = _serialize_lead(row)
            summary = str(lead.get("qualification_summary") or "").strip()
            next_step = str(lead.get("proximo_passo") or "").strip().lower()
            completed_at = lead.get("qualification_completed_at")
            has_handoff = "consultor" in next_step or "consultor" in summary.lower()
            if not (completed_at or summary or has_handoff):
                continue

            final_status = "qualificado" if _is_qualified_lead(lead) else "novo"
            cursor.execute(
                "UPDATE leads SET status = ?, updated_at = ? WHERE session_id = ?",
                (final_status, datetime.now().isoformat(), lead["session_id"]),
            )
            repaired.append({"session_id": lead["session_id"], "status": final_status})

        conn.commit()
        return {"repaired_count": len(repaired), "repaired": repaired}
    except Exception as exc:
        conn.rollback()
        return {"repaired_count": 0, "repaired": [], "error": str(exc)}
    finally:
        conn.close()


def update_lead(lead_id: int, data: dict) -> bool:
    """Atualiza um lead pelo ID."""
    conn = get_db()
    cursor = conn.cursor()

    try:
        normalized = _normalize_contact_fields(data)
        updates = []
        values = []
        for key, value in normalized.items():
            if key not in ("id", "session_id", "created_at"):
                updates.append(f"{key} = ?")
                values.append(value)

        if updates:
            updates.append("updated_at = ?")
            values.append(datetime.now().isoformat())
            values.append(lead_id)

            query = f"UPDATE leads SET {', '.join(updates)} WHERE id = ?"
            cursor.execute(query, values)

            cursor.execute("SELECT * FROM leads WHERE id = ?", (lead_id,))
            updated = cursor.fetchone()
            if updated:
                status = "qualificado" if _is_qualified_lead(updated) else "novo"
                cursor.execute("UPDATE leads SET status = ? WHERE id = ?", (status, lead_id))

            conn.commit()
            return True
        return False
    except Exception as exc:
        print(f"Erro ao atualizar lead: {exc}")
        conn.rollback()
        return False
    finally:
        conn.close()


def delete_lead(lead_id: int) -> bool:
    """Exclui um lead pelo ID."""
    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
        if cursor.rowcount > 0:
            conn.commit()
            return True
        return False
    except Exception as exc:
        print(f"Erro ao excluir lead: {exc}")
        conn.rollback()
        return False
    finally:
        conn.close()


def _normalize_contact_fields(lead_info: dict) -> dict:
    normalized = dict(lead_info or {})

    if normalized.get("name") and not normalized.get("contato"):
        normalized["contato"] = normalized.get("name")
    if normalized.get("phone") and not normalized.get("telefone"):
        normalized["telefone"] = normalized.get("phone")

    email = str(normalized.get("email", "")).strip()
    telefone = str(normalized.get("telefone", "")).strip()
    legacy = str(normalized.get("email_telefone", "")).strip()

    if legacy:
        if not email and EMAIL_PATTERN.match(legacy):
            email = legacy
        elif not telefone:
            telefone = legacy

    normalized["email"] = email
    normalized["telefone"] = telefone
    normalized["phone_normalized"] = normalize_phone(telefone)
    normalized["channel_id"] = str(normalized.get("channel_id", "")).strip()
    normalized["email_telefone"] = _build_email_phone_summary(email, telefone)
    return normalized


def normalize_phone(phone: str) -> str:
    return re.sub(r"\D+", "", str(phone or ""))


def phone_variants(phone: str) -> set[str]:
    normalized = normalize_phone(phone)
    if not normalized:
        return set()

    variants = {normalized}
    if normalized.startswith("55") and len(normalized) >= 12:
        local = normalized[2:]
        variants.add(local)
    elif len(normalized) in {10, 11}:
        local = normalized
        variants.add(f"55{local}")
    else:
        local = normalized

    if len(local) == 11 and local[2] == "9":
        without_mobile_digit = f"{local[:2]}{local[3:]}"
        variants.add(without_mobile_digit)
        variants.add(f"55{without_mobile_digit}")
    elif len(local) == 10:
        with_mobile_digit = f"{local[:2]}9{local[2:]}"
        variants.add(with_mobile_digit)
        variants.add(f"55{with_mobile_digit}")

    return variants


def phones_match(left: str, right: str) -> bool:
    left_variants = phone_variants(left)
    right_variants = phone_variants(right)
    if not left_variants or not right_variants:
        return False
    if left_variants.intersection(right_variants):
        return True

    for left_value in left_variants:
        for right_value in right_variants:
            shorter, longer = sorted((left_value, right_value), key=len)
            if len(shorter) >= 10 and longer.endswith(shorter):
                return True
    return False


def _build_email_phone_summary(email: str, telefone: str) -> str:
    parts = [part for part in (email.strip(), telefone.strip()) if part]
    return " | ".join(parts)


def _is_qualified_lead(lead_data: Optional[dict]) -> bool:
    if not lead_data:
        return False
    required_fields = ("cnpj", "contato", "email", "telefone", "segmento")
    return all(str(_get_lead_value(lead_data, field)).strip() for field in required_fields)


def is_qualified_lead_data(lead_data: Optional[dict]) -> bool:
    return _is_qualified_lead(lead_data)


def _resolve_next_status(lead_data: Optional[dict], current_status: str = "") -> str:
    status = str(current_status or "").strip()
    if status == "INACTIVE":
        return "INACTIVE"
    if status == "ACTIVE":
        return "ACTIVE"
    return "qualificado" if _is_qualified_lead(lead_data) else "novo"


def _get_lead_value(lead_data, field: str) -> str:
    if isinstance(lead_data, dict):
        return str(lead_data.get(field, ""))
    try:
        return str(lead_data[field])
    except Exception:
        return ""


def _serialize_lead(row: sqlite3.Row) -> dict:
    email = row["email"] if "email" in row.keys() else ""
    telefone = row["telefone"] if "telefone" in row.keys() else ""
    phone_normalized = row["phone_normalized"] if "phone_normalized" in row.keys() else normalize_phone(telefone)
    channel_id = row["channel_id"] if "channel_id" in row.keys() else ""
    qualification_summary = row["qualification_summary"] if "qualification_summary" in row.keys() else ""
    qualification_completed_at = (
        row["qualification_completed_at"] if "qualification_completed_at" in row.keys() else None
    )
    email_telefone = row["email_telefone"] if "email_telefone" in row.keys() else _build_email_phone_summary(email, telefone)

    if not email_telefone:
        email_telefone = _build_email_phone_summary(email, telefone)

    return {
        "id": row["id"],
        "session_id": row["session_id"],
        "empresa": row["empresa"],
        "contato": row["contato"],
        "cnpj": row["cnpj"],
        "email": email,
        "telefone": telefone,
        "phone_normalized": phone_normalized,
        "channel_id": channel_id,
        "email_telefone": email_telefone,
        "segmento": row["segmento"],
        "produtos_interesse": row["produtos_interesse"],
        "volume_compra": row["volume_compra"],
        "fornecedor_atual": row["fornecedor_atual"],
        "dores_necessidades": row["dores_necessidades"],
        "decisores": row["decisores"],
        "proximo_passo": row["proximo_passo"],
        "qualification_summary": qualification_summary,
        "qualification_completed_at": qualification_completed_at,
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
