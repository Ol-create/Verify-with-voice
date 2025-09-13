from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings

# Enable pooling
engine = create_engine(
    settings.DATABASE_URL,
    pool_size=10,          # max open connections
    max_overflow=20,       # extra connections if pool is full
    pool_timeout=30,       # wait time before giving up
    pool_recycle=1800,     # recycle connections (secs)
    echo=False,            # set to True for SQL debugging
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
