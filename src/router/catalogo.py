"""Acceso de solo lectura al catálogo de productos."""

import os
import re
from typing import Any

from dotenv import load_dotenv
from psycopg import connect
from psycopg.rows import dict_row

load_dotenv()


def consultar_catalogo(sql: str, parametros: tuple[Any, ...] = ()) -> list[dict[str, Any]] | str:
    """Ejecuta un SELECT parametrizado y cierra la conexión al terminar."""
    consulta_normalizada = sql.strip().upper()
    palabras_prohibidas = r"\b(INSERT|UPDATE|DELETE|MERGE|CREATE|ALTER|DROP|TRUNCATE|GRANT|REVOKE|COPY|CALL|DO)\b"
    if (
        not consulta_normalizada.startswith("SELECT")
        or ";" in consulta_normalizada
        or "FOR UPDATE" in consulta_normalizada
        or re.search(palabras_prohibidas, consulta_normalizada)
    ):
        raise ValueError("El catálogo solo permite consultas SELECT.")

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        return "catálogo no disponible"

    try:
        with connect(database_url, connect_timeout=5, row_factory=dict_row) as conexion:
            with conexion.cursor() as cursor:
                cursor.execute(sql, parametros)
                return list(cursor.fetchall())
    except Exception:
        return "catálogo no disponible"
