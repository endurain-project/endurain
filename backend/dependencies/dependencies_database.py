from database import SessionLocal

def get_db():
    # Create a new database session and return it
    db = SessionLocal()
    
    try:
        # Yield the database session
        yield db
    finally:
        # Close the database session
        db.close()