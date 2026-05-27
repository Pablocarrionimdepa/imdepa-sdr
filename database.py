"""
Modulo de banco de dados SQLite para armazenamento de leads.
"""

import os
import re
import sqlite3
from datetime import datetime
from typing import Optional

DB_PATH = os.getenv("DB_PATH", "leads.db")


EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def get_db():
    """Retorna uma conexao com o banco de dados."""
    conn = sqlite3.connect(DB_PATH)
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
                status = "qualificado" if _is_qualified_lead(updated) else "novo"
                cursor.execute(
                    "UPDATE leads SET status = ? WHERE session_id = ?",
                    (status, session_id),
                )
        else:
            status = "qualificado" if _is_qualified_lead(normalized) else "novo"
            now = datetime.now().isoformat()
            cursor.execute(
                """
                INSERT INTO leads (
                    session_id, empresa, contato, cnpj, email, telefone, email_telefone, segmento,
                    produtos_interesse, volume_compra, fornecedor_atual,
                    dores_necessidades, decisores, proximo_passo, status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    normalized.get("empresa", ""),
                    normalized.get("contato", ""),
                    normalized.get("cnpj", ""),
                    normalized.get("email", ""),
                    normalized.get("telefone", ""),
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
    normalized["email_telefone"] = _build_email_phone_summary(email, telefone)
    return normalized


def _build_email_phone_summary(email: str, telefone: str) -> str:
    parts = [part for part in (email.strip(), telefone.strip()) if part]
    return " | ".join(parts)


def _is_qualified_lead(lead_data: Optional[dict]) -> bool:
    if not lead_data:
        return False
    required_fields = ("cnpj", "contato", "email", "telefone", "segmento")
    return all(str(_get_lead_value(lead_data, field)).strip() for field in required_fields)


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
