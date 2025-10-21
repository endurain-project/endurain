import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.engine.url import URL

import core.config as core_config


# Fetch the database type (e.g., mariadb or postgresql)
db_type = os.environ.get("DB_TYPE", "postgres").lower()

# Define supported database drivers
supported_drivers = {"mariadb": "mysql+mysqldb", "postgres": "postgresql+psycopg"}

if db_type not in supported_drivers:
    raise ValueError(
        f"Unsupported DB_TYPE: {db_type}. Supported types are {list(supported_drivers.keys())}"
    )

# Define the database connection URL using environment variables
db_url = URL.create(
    drivername=supported_drivers[db_type],
    username=os.environ.get("DB_USER", "endurain"),
    password=core_config.read_secret("DB_PASSWORD"),
    host=os.environ.get("DB_HOST", "postgres"),
    port=os.environ.get("DB_PORT", "5432"),
    database=os.environ.get("DB_DATABASE", "endurain"),
)

# Create the SQLAlchemy engine
engine = create_engine(
    db_url, pool_size=10, max_overflow=20, pool_timeout=180, pool_recycle=3600
)

# Create a session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create a base class for declarative models
Base = declarative_base()


def get_db():
    # Create a new database session and return it
    db = SessionLocal()

    try:
        # Yield the database session
        yield db
    finally:
        # Close the database session
        db.close()
