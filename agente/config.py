"""Configuración leída de variables de entorno (.env). Nunca se guardan credenciales en el código."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

RAIZ = Path(__file__).resolve().parent.parent
if load_dotenv:
    load_dotenv(RAIZ / ".env")


@dataclass(frozen=True)
class Config:
    # Data Mart (rol de solo lectura del agente)
    pg_host: str = os.getenv("PG_HOST", "localhost")
    pg_port: int = int(os.getenv("PG_PORT", "5432"))
    pg_db: str = os.getenv("PG_DB", "parcial01")
    pg_user: str = os.getenv("PG_USER", "agente_lector")
    pg_password: str = os.getenv("PG_PASSWORD", "")
    # Usuario administrador: sólo lo usa scripts/setup_datamart.py para crear y cargar el Data Mart
    pg_admin_user: str = os.getenv("PG_ADMIN_USER", "postgres")
    pg_admin_password: str = os.getenv("PG_ADMIN_PASSWORD", "")
    # LLM vía OpenRouter (API compatible con OpenAI)
    openrouter_api_key: str = os.getenv("OPENROUTER_API_KEY", "")
    openrouter_model: str = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
    openrouter_base_url: str = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    llm_timeout: float = float(os.getenv("LLM_TIMEOUT", "25"))
    # auto = LLM si hay API key y, si falla, reglas | llm = sólo LLM | reglas = sólo reglas
    modo_interprete: str = os.getenv("MODO_INTERPRETE", "auto")
    # BDOO (ZODB)
    zodb_path: Path = Path(os.getenv("ZODB_PATH", str(RAIZ / "data" / "bdoo" / "agente.fs")))
    zodb_blobs: Path = Path(os.getenv("ZODB_BLOBS", str(RAIZ / "data" / "bdoo" / "blobs")))

    @property
    def llm_disponible(self) -> bool:
        return bool(self.openrouter_api_key)

    def dsn(self, admin: bool = False) -> str:
        user = self.pg_admin_user if admin else self.pg_user
        pwd = self.pg_admin_password if admin else self.pg_password
        partes = [f"host={self.pg_host}", f"port={self.pg_port}", f"dbname={self.pg_db}", f"user={user}"]
        if pwd:
            partes.append(f"password={pwd}")
        return " ".join(partes)


CONFIG = Config()
