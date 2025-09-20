# db.py
from datetime import date, datetime
from sqlalchemy import create_engine, Column, String, Integer, Date, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

Base = declarative_base()
engine = create_engine("sqlite:///tanks.db", echo=False, future=True)
SessionLocal = sessionmaker(bind=engine)

# ---- Tables ----
class Tank(Base):
    __tablename__ = "tanks"
    serial = Column(String, primary_key=True)
    status = Column(String, default="in")  # in | out
    last_movement_date = Column(Date, nullable=True)

    movements = relationship("Movement", back_populates="tank")

class Movement(Base):
    __tablename__ = "movements"
    id = Column(Integer, primary_key=True, autoincrement=True)
    serial = Column(String, ForeignKey("tanks.serial"))
    movement_type = Column(String)  # dispatch | receipt
    movement_date = Column(Date)
    project = Column(String, nullable=True)
    responsible_engineer = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    tank = relationship("Tank", back_populates="movements")

# ---- Setup ----
def init_db():
    Base.metadata.create_all(engine)

def seed_tanks(serials: list[str]):
    session = SessionLocal()
    for s in serials:
        if not session.get(Tank, s):
            session.add(Tank(serial=s, status="in"))
    session.commit()
    session.close()

# ---- Helpers ----
def get_all_tanks():
    session = SessionLocal()
    tanks = session.query(Tank).all()
    session.close()
    return tanks

def get_movements(serial=None):
    session = SessionLocal()
    q = session.query(Movement)
    if serial:
        q = q.filter(Movement.serial == serial)
    moves = q.order_by(Movement.movement_date.desc()).all()
    session.close()
    return moves

def create_movement(serial, movement_type, movement_date, project=None, engineer=None):
    session = SessionLocal()
    tank = session.get(Tank, serial)
    if not tank:
        session.close()
        raise ValueError(f"Tank {serial} does not exist")

    # Validation
    if movement_type == "dispatch":
        if tank.status == "out":
            session.close()
            raise ValueError("Tank already out, cannot dispatch again")
        if not project or not engineer:
            session.close()
            raise ValueError("Project and engineer required for dispatch")
        tank.status = "out"
    elif movement_type == "receipt":
        if tank.status == "in":
            session.close()
            raise ValueError("Tank already in, cannot receipt")
        tank.status = "in"
    else:
        session.close()
        raise ValueError("Invalid movement type")

    tank.last_movement_date = movement_date
    move = Movement(
        serial=serial,
        movement_type=movement_type,
        movement_date=movement_date,
        project=project,
        responsible_engineer=engineer,
    )
    session.add(move)
    session.commit()
    session.close()
    return move
