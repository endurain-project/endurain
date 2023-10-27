from fastapi import FastAPI
from apscheduler.schedulers.background import BackgroundScheduler
from controllers import sessionController, userController, gearController, activitiesController
import logging
#from db.db import User  # Import your SQLAlchemy session management from db.db

app = FastAPI()

logger = logging.getLogger("myLogger")
logger.setLevel(logging.DEBUG)

file_handler = logging.FileHandler('app.log')
file_handler.setLevel(logging.DEBUG)

formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)

logger.addHandler(file_handler)

# Router files
app.include_router(sessionController.router)
app.include_router(userController.router)
app.include_router(gearController.router)
app.include_router(activitiesController.router)

# Create a background scheduler instance
scheduler = BackgroundScheduler()
scheduler.start()

# Remove the leading space
scheduler.add_job(sessionController.remove_expired_tokens, 'interval', minutes=1)

# Add the background scheduler to the app's shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    scheduler.shutdown()
