from database import SessionLocal

def get_db():
    # get DB ssession
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()