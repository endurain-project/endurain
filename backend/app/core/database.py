import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.engine.url import URL


# Helper to fetch environment variables
def get_env_variable(var_name: str) -> str:
    value = os.environ.get(var_name)
    if value is None:
        raise EnvironmentError(f"Environment variable {var_name} is not set")
    return value


# Define the database connection URL using environment variables
db_url = URL.create(
    drivername="mysql",
    username=get_env_variable("DB_USER"),
    password=get_env_variable("DB_PASSWORD"),
    host=get_env_variable("DB_HOST"),
    port=get_env_variable("DB_PORT"),
    database=get_env_variable("DB_DATABASE"),
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
