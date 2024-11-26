import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.engine.url import URL


def get_db():
    # Create a new database session and return it
    db = SessionLocal()

    try:
        # Yield the database session
        yield db
    finally:
        # Close the database session
        db.close()


# Define the database connection URL using environment variables
db_url = URL.create(
    drivername="mysql",
    username=os.environ.get("DB_USER"),
    password=os.environ.get("DB_PASSWORD"),
    host=os.environ.get("DB_HOST"),
    port=os.environ.get("DB_PORT"),
    database=os.environ.get("DB_DATABASE"),
)

# Create the SQLAlchemy engine
engine = create_engine(
    db_url, pool_size=10, max_overflow=20, pool_timeout=180, pool_recycle=3600
)

# Create a session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create a base class for declarative models
Base = declarative_base()
