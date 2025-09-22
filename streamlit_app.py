# db.py — now supports hosted Postgres via DATABASE_URL (st.secrets or env)
from __future__ import annotations
from datetime import date, datetime
import os, re
from typing import Optional, List, Dict
from sqlalchemy import create_engine, Column, String, Integer, Date, DateTime, ForeignKey, text
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

def _database_url() -> str:
    # Prefer Streamlit Cloud secrets; fall back to env var; default to local SQLite
    url = None
    try:
        import streamlit as st  # available at runtime in Streamlit
        url = st.secrets.get("DATABASE_URL")
    except Exception:
        pass
    url = url or os.getenv("DATABASE_URL")
    return url or "sqlite:///tanks.db"

DATABASE_URL = _database_url()

# Important for Neon/Supabase: sslmode is typically required; include in your secret URL
engine = create_engine(
    DATABASE_URL,
    echo=False,
    future=True,
    pool_pre_ping=True,  # keeps the pool healthy on serverless Postgres
)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

# ----------------- Tablas -----------------
class Tank(Base):
    __tablename__ = "tanks"
    serial = Column(String, primary_key=True)
    status = Column(String, default="in")                 # 'in' | 'out'
    last_movement_date = Column(Date, nullable=True)
    movements = relationship("Movement", back_populates="tank", cascade="all, delete-orphan")

class Movement(Base):
    __tablename__ = "movements"
    id = Column(Integer, primary_key=True, autoincrement=True)
    serial = Column(String, ForeignKey("tanks.serial"), nullable=False)
    movement_type = Column(String, nullable=False)        # 'dispatch' | 'receipt'
    movement_date = Column(Date, nullable=False)
    project = Column(String, nullable=True)
    responsible_engineer = Column(String, nullable=True)
    responsible_contractor = Column(String, nullable=True)
    smt_number = Column(String, nullable=True)            # obligatorio (5 dígitos)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    tank = relationship("Tank", back_populates="movements")

# ----------------- Setup + “migración” simple -----------------
def init_db():
    """Create tables if they don't exist; add new columns to old DBs (SQLite or Postgres)."""
    Base.metadata.create_all(engine)
    _ensure_migrations()

def _ensure_migrations():
    # Add columns to movements table if they’re missing (works on SQLite & Postgres)
    with engine.begin() as conn:
        def has_col(table: str, col: str) -> bool:
            # portable check: use information_schema for Postgres; PRAGMA for SQLite
            url = str(engine.url)
            if url.startswith("sqlite"):
                rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
                return any(r[1] == col for r in rows)
            else:
                q = text("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = :t
                """)
                rows = conn.execute(q, {"t": table}).fetchall()
                return any(r[0] == col for r in rows)

        if not has_col("movements", "responsible_contractor"):
            conn.execute(text("ALTER TABLE movements ADD COLUMN responsible_contractor TEXT"))
        if not has_col("movements", "smt_number"):
            conn.execute(text("ALTER TABLE movements ADD COLUMN smt_number TEXT"))

def seed_tanks(serials: list[str]):
    """Create tanks if not present. Safe to call every startup."""
    session = SessionLocal()
    try:
        for s in serials:
            if not session.get(Tank, s):
                session.add(Tank(serial=s, status="in", last_movement_date=None))
        session.commit()
    finally:
        session.close()

# ----------------- Queries / Actions -----------------
def get_all_tanks():
    session = SessionLocal()
    try:
        return session.query(Tank).order_by(Tank.serial).all()
    finally:
        session.close()

def get_movements(serial: Optional[str] = None):
    session = SessionLocal()
    try:
        q = session.query(Movement)
        if serial:
            q = q.filter(Movement.serial == serial)
        return q.order_by(Movement.movement_date.desc(), Movement.id.desc()).all()
    finally:
        session.close()

def _validate_smt_required_5_digits(smt_number: Optional[str]) -> str:
    smt = (smt_number or "").strip()
    if not re.fullmatch(r"\d{5}", smt):
        raise ValueError("El Número de SMT es obligatorio y debe tener exactamente 5 dígitos.")
    return smt

def create_movement(
    serial: str,
    movement_type: str,               # 'dispatch' | 'receipt'
    movement_date: date,
    project: Optional[str] = None,
    engineer: Optional[str] = None,
    contractor: Optional[str] = None,
    smt_number: Optional[str] = None,
):
    session = SessionLocal()
    try:
        tank = session.get(Tank, serial)
        if not tank:
            raise ValueError(f"El tanque {serial} no existe")

        if movement_date > date.today():
            raise ValueError("La fecha del movimiento no puede estar en el futuro")

        smt_str = _validate_smt_required_5_digits(smt_number)

        if movement_type == "dispatch":
            if tank.status == "out":
                raise ValueError("El tanque ya está fuera: no se puede despachar de nuevo")
            if not project or not engineer or not contractor:
                raise ValueError("Despacho requiere Proyecto, Ingeniero responsable y Contratista responsable")
            tank.status = "out"
        elif movement_type == "receipt":
            if tank.status == "in":
                raise ValueError("El tanque ya está en almacén: no se puede recepcionar")
        else:
            raise ValueError("Tipo de movimiento inválido")

        tank.last_movement_date = movement_date

        move = Movement(
            serial=serial,
            movement_type=movement_type,
            movement_date=movement_date,
            project=project or None,
            responsible_engineer=engineer or None,
            responsible_contractor=contractor or None,
            smt_number=smt_str,
        )
        session.add(move)
        session.commit()
        return move
    finally:
        session.close()

def summary_current_out_by_engineer() -> List[Dict[str, str | int]]:
    session = SessionLocal()
    try:
        out_tanks = session.query(Tank).filter(Tank.status == "out").all()
        counts: Dict[str, int] = {}
        for t in out_tanks:
            last = (
                session.query(Movement)
                .filter(Movement.serial == t.serial)
                .order_by(Movement.movement_date.desc(), Movement.id.desc())
                .first()
            )
            if last and last.movement_type == "dispatch":
                eng = last.responsible_engineer or "(sin ingeniero)"
                counts[eng] = counts.get(eng, 0) + 1
        return [{"responsible_engineer": k, "count": v} for k, v in sorted(counts.items(), key=lambda x: (-x[1], x[0]))]
    finally:
        session.close()
