from datetime import datetime
from time import time
import jwt
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import OAuth2AuthorizationCodeBearer
from pydantic import BaseModel
import requests
import uvicorn
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.models import Info
from fastapi.openapi.models import ExternalDocumentation

app = FastAPI(title="Membership API's",
              openapi_url="/api/openapi.json",
              docs_url="/docs",
              redoc_url="/redoc",
              version="1.0",
              description="Your API description",
              info=Info(
                  title="Membership API's",
                  version="1.0",
                  description="Your API description",
              ),
              external_docs=ExternalDocumentation(
                  url="http://127.0.0.1:8000/docs",
                  description="Your external documentation description",
              ),
              )

# Enable CORS for all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # You may want to restrict this to specific origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Replace with your actual Zoom app credentials
ZOOM_CLIENT_ID = "MaVSlD7wRYysIDsHzkmQ"
ZOOM_ACCOUNT_ID = "g5pe1GVtRAyIkEi-sFwF2g"
ZOOM_CLIENT_SECRET = "n4sUfxElBmC9m82UPo9oiZtUBblu64ic"

ZOOM_AUTH_TOKEN_URL = "https://zoom.us/oauth/token"
ZOOM_API_BASE_URL = "https://api.zoom.us/v2"

# Database to store registered users (in-memory for simplicity)
registered_users = set()
# Store the meeting details
meetings_database = {}

# Store the users who joined the meeting
joined_users = []



class UserRegistration(BaseModel):
    username: str


class ZoomClient:
    def __init__(self, client_id, client_secret):
        self.client_id = client_id
        self.client_secret = client_secret

    def get_access_token(self):
        data = {
            "grant_type": "account_credentials",
            "account_id": ZOOM_ACCOUNT_ID,
            "client_secret": ZOOM_CLIENT_SECRET
        }
        auth = (self.client_id, self.client_secret)
        response = requests.post(ZOOM_AUTH_TOKEN_URL, auth=auth, data=data)

        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="Unable to get access token")

        response_data = response.json()
        return response_data["access_token"]

    def create_meeting(self, topic: str, duration: int, start_date: str, start_time: str,
                       access_token: str = Depends(get_access_token)):
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        payload = {
            "topic": topic,
            "duration": duration,
            'start_time': f'{start_date}T10:{start_time}',
            # 'start_time':datetime.strptime(start_time, "%Y-%m-%d %H:%M"),
            'start_date':start_date,
            'user_id': "me",
            "type": 2
        }

        resp = requests.post(f"{ZOOM_API_BASE_URL}/users/me/meetings", headers=headers, json=payload)

        if resp.status_code != 201:
            raise HTTPException(status_code=400, detail="Unable to generate meeting link")

        response_data = resp.json()
        # Store the meeting details in the database
        meeting_id = response_data["id"]
        meetings_database[meeting_id] = {
            "meeting_url": response_data["join_url"],
            "password": response_data["password"],
            "meetingTime": response_data["start_time"],
            "purpose": response_data["topic"],
            "duration": response_data["duration"],
            "status": 1
        }

        content = {
            "meeting_url": response_data["join_url"],
            "password": response_data["password"],
            "meetingTime": response_data["start_time"],
            "purpose": response_data["topic"],
            "duration": response_data["duration"],
            "message": "Success",
            "status": 1,
            "meeting_id": response_data["id"]
        }

        return content


zoom_client = ZoomClient(ZOOM_CLIENT_ID, ZOOM_CLIENT_SECRET)


# def create_auth_signature(meeting_id, role):
#     ZOOM_SDK_CLIENT_ID = ("go4JMXwT_Kh_Fb5VHUUrA", "")
#     ZOOM_SDK_CLIENT_SECRET = ("E5ce3pknEQ17s3ZreKnRlN6R8yCLcWH9", "")
#
#     iat = time()
#     exp = iat + 60 * 60 * 1  # expire after 1 hour
#
#     oHeader = {"alg": 'HS256', "typ": 'JWT'}
#
#     oPayload = {
#         "sdkKey": ZOOM_SDK_CLIENT_ID,
#         "mn": int(meeting_id),
#         "role": role,
#         "iat": iat,
#         "exp": exp,
#         "tokenExp": exp
#     }
#
#     jwtEncode = jwt.encode(
#         oPayload,
#         ZOOM_SDK_CLIENT_SECRET,
#         algorithm="HS256",
#         headers=oHeader,
#     )

    # return {'token': jwtEncode, 'sdkKey': ZOOM_SDK_CLIENT_ID}


# # Modify your existing MeetingAuthorizationView to use the get_current_user dependency
# class MeetingAuthorizationView(BaseModel):
#     meeting_id: str
#     role: int



@app.post("/register", response_model=dict)
async def register_user(user: UserRegistration):
    registered_users.add(user.username)
    return {"message": "User registered successfully"}


# Endpoint to fetch registered users
@app.get("/registered-users")
async def get_registered_users():
    return list(registered_users)


# FastAPI endpoint to create a Zoom meeting
@app.post("/users/me/meetings", response_model=dict)
async def create_meeting_endpoint(
        topic: str,
        duration: int,
        start_date: str,
        start_time: str,
        access_token: str = Depends(zoom_client.get_access_token)):
    return zoom_client.create_meeting(topic, duration, start_date, start_time, access_token)


# @app.post("/meeting/authorize", response_model=dict)
# async def meeting_authorization(payload: MeetingAuthorizationView,
# ):
#     meeting_id = payload.meeting_id
#     role = payload.role
#     # Assuming meeting details are saved in the database, replace this with your logic
#     # password = get_password_from_database(meeting_no)
#     password = meetings_database["password"]
#
#     response = create_auth_signature(meeting_id, role)
#     response['meeting_id'] = meeting_id
#     response['password'] = password
#     return response

@app.post("/join-meeting/{meeting_id}/{username}", response_model=dict)
async def join_meeting(meeting_id: int, username: str):
    if username not in registered_users:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not registered")

    # Check if the meeting ID exists in the database
    if meeting_id not in meetings_database:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No meeting available to join",
        )

    meeting_details = meetings_database[meeting_id]
    # Check if the user has already joined
    if username in joined_users:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User has already joined the meeting",
        )
    # Add the username to the list of joined users
    joined_users.append(username)

    # Include additional logic here to perform actions related to joining the meeting
    # For now, just returning the stored meeting details with a "joined successfully" message
    return {"message": "Joined successfully", "meeting_details": meeting_details}


# Endpoint to get the list of joined users (for demonstration purposes)
@app.get("/joined-users", response_model=list)
async def get_joined_users():
    return joined_users


# Run the FastAPI application
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
