import os
from stravalib.client import Client
from dotenv import load_dotenv

router = APIRouter()

logger = logging.getLogger("myLogger")

# Load the environment variables from config/.env
load_dotenv('config/.env')

#stravaClient = Client()
#access_token = client.exchange_code_for_token(
#    client_id=os.getenv("STRAVA_CLIENT_ID"),
#    client_secret=os.getenv("STRAVA_CLIENT_SECRET"),
#    code=os.getenv("STRAVA_AUTH_CODE"),
#)

#stravaClient = Client(access_token=access_token)
#athlete = client.get_athlete()
#activities = client.get_activities(limit=10)

#for activity in activities:
#    print(activity.name)

@app.get("/strava/strava-auth")
async def start_strava_auth(request: Request):
    client = Client()
    authorize_url = client.authorization_url(
        client_id=os.getenv("STRAVA_CLIENT_ID"), redirect_uri="http://localhost:8282/authorized"
    )
    return RedirectResponse(url=authorize_url)

@app.get("/strava/authorized")
async def handle_strava_callback(request: Request):
    # retrieve code parameter from request
    code = request.query_params.get("code")

    # create token
    token_response = client.exchange_code_for_token(
        client_id=os.getenv("STRAVA_CLIENT_ID"), client_secret=os.getenv("STRAVA_CLIENT_SECRET"), code=code
    )

    # store access_token to variable
    access_token = token_response["access_token"]
    # store refresh_token to variable
    refresh_token = token_response["refresh_token"]
    expires_at = token_response["expires_at"]

    from . import userController
    
    # Store the 'code' somewhere or initiate the token exchange process
    return {"message": "Authorization code received. You can now exchange it for an access token."}
