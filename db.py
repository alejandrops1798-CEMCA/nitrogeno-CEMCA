# db.py — Soporta Postgres (Neon) vía DATABASE_URL y hace fallback a SQLite local.
from __future__ import annotations
from datetime import date, datetime
import os, re
from typing import Optional, List, Dict
from sqlalchemy import (
    create_engine, Column, String, Integer, Date, DateTime, ForeignKey, text
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

def _database_url() -> str:
    url = None
    in_cloud = os.getenv("STREAMLIT_RUNTIME", "").lower() == "cloud"
    try:
        import streamlit as st
        if hasattr(st, "secrets"):
            url = st.secrets.get("DATABASE_URL")
    except Exception:
        pass
    url = url or os.getenv("DATABASE_URL")
    if in_cloud and not url:
        raise RuntimeError(
            "DATABASE_URL no está configurado en Streamlit Cloud Secrets. "
            "Se rechaza usar SQLite en producción para evitar pérdida de datos."
        )
    return url or "sqlite:///tanks.db"

DATABASE_URL = _database_url()

engine = create_engine(
    DATABASE_URL,
    echo=False,
    future=True,
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class Tank(Base):
    __tablename__ = "tanks"
    serial = Column(String, primary_key=True)
    status = Column(String, default="in")  # 'in' | 'out'
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
    smt_number = Column(String, nullable=True)            # validado en create_movement
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    tank = relationship("Tank", back_populates="movements")

def init_db():
    Base.metadata.create_all(engine)
    _ensure_migrations()

def _ensure_migrations():
    with engine.begin() as conn:
        url_str = str(engine.url)

        def has_col_sqlite(table: str, col: str) -> bool:
            rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
            return any(r[1] == col for r in rows)

        def has_col_postgres(table: str, col: str) -> bool:
            q = text("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = :t AND table_schema = 'public'
            """)
            rows = conn.execute(q, {"t": table}).fetchall()
            return any(r[0] == col for r in rows)

        def has_col(table: str, col: str) -> bool:
            if url_str.startswith("sqlite"):
                return has_col_sqlite(table, col)
            else:
                return has_col_postgres(table, col)

        if not has_col("movements", "responsible_contractor"):
            conn.execute(text("ALTER TABLE movements ADD COLUMN responsible_contractor TEXT"))
        if not has_col("movements", "smt_number"):
            conn.execute(text("ALTER TABLE movements ADD COLUMN smt_number TEXT"))

def seed_tanks(serials: List[str]):
    session = SessionLocal()
    try:
        for s in serials:
            if not session.get(Tank, s):
                session.add(Tank(serial=s, status="in", last_movement_date=None))
        session.commit()
    finally:
        session.close()

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
    """
    Reglas:
    - SMT obligatorio (5 dígitos)
    - No despachar si el tanque ya está 'out'
    - No recepcionar si el tanque ya está 'in'
    - En 'dispatch' se requieren: project, engineer, contractor
    - Fecha futura no permitida
    """
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
            tank.status = "in"

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
            updated_at=datetime.utcnow(),
        )
        session.add(move)
        session.commit()
        return move
    finally:
        session.close()

def summary_current_out_by_engineer() -> List[Dict[str, str | int]]:
    """Conteo de tanques actualmente 'out' por ingeniero del ÚLTIMO despacho."""
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
        return [
            {"responsible_engineer": k, "count": v}
            for k, v in sorted(counts.items(), key=lambda x: (-x[1], x[0]))
        ]
    finally:
        session.close()

# ========= NUEVO: Reparar estados según historial =========
def recompute_tank_states_from_history() -> int:
    """
    Recorre cada tanque, busca su último movimiento y ajusta:
      - Tank.status = 'out' si el último movimiento fue 'dispatch', si no 'in'
      - Tank.last_movement_date = fecha del último movimiento
    Devuelve la cantidad de tanques actualizados.
    """
    session = SessionLocal()
    updated = 0
    try:
        tanks = session.query(Tank).all()
        for t in tanks:
            last = (
                session.query(Movement)
                .filter(Movement.serial == t.serial)
                .order_by(Movement.movement_date.desc(), Movement.id.desc())
                .first()
            )
            if not last:
                continue
            new_status = "out" if last.movement_type == "dispatch" else "in"
            new_date = last.movement_date
            if t.status != new_status or t.last_movement_date != new_date:
                t.status = new_status
                t.last_movement_date = new_date
                updated += 1
        session.commit()
        return updated
    finally:
        session.close()
