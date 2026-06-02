"""
Modulo de banco de dados SQLite para armazenamento de leads.
"""

import os
import re
import sqlite3
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

    conn.commit()
    conn.close()
    print("Banco de dados inicializado com sucesso.")


def save_lead(session_id: str, lead_info: dict) -> bool:
    """Salva ou atualiza informacoes do lead."""
    conn = get_db()
    cursor = conn.cursor()

    try:
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

            for json_key, db_col in field_mapping.items():
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


def get_lead_by_session(session_id: str) -> Optional[dict]:
    """Retorna um lead pelo session_id."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM leads WHERE session_id = ?", (session_id,))
    row = cursor.fetchone()

    conn.close()
    return _serialize_lead(row) if row else None


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
        if row_phone_normalized == normalized_phone or normalize_phone(row_phone) == normalized_phone:
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
        return "INACTIVE" if _is_qualified_lead(lead_data) else "ACTIVE"
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
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
