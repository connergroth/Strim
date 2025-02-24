import os 
import json
import time
import requests
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("STRAVA_CLIENT_ID")
CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET")
REFRESH_TOKEN = os.getenv("STRAVA_REFRESH_TOKEN")

def get_access_token():
    url = "https://www.strava.com/oauth/token"
    params = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": REFRESH_TOKEN,
        "grant_type": "refresh_token"
    }
    response = requests.post(url, data=params)
    data = response.json()

    if "access_token" not in data:
        raise Exception(f"Error recieving access token: {data}")

    print(f"New access token: {access_token}") 
    return data["access_token"]

def delete_activity(activity_id, access_token):
    url = f"https://www.strava.com/api/v3/activities/{activity_id}"
    headers = {"Authorization": f"Bearer {access_token}"}

    response = requests.delete(url, headers=headers)

    if response.status_code == 204:
        print(f"Activity {activity_id} deleted successfully.")
    else:
        print(f"Failed to delete activity {activity_id}")
    
import logging

def get_activity_details(activity_id):
    access_token = get_access_token()
    url = f"https://www.strava.com/api/v3/activities/{activity_id}"
    headers = {"Authorization": f"Bearer {access_token}"}

    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        activity_data = response.json()
        with open(f"activity_{activity_id}.json", "w") as f:
            json.dump(activity_data, f, indent=4)

        logging.info(f"Saved activity {activity_id} metadata.")
        return activity_data
    else:
        logging.error(f"Failed to retrieve activity {activity_id}: {response.json()}")
        return None


def create_activity(access_token, metadata):
    url = "https://www.strava.com/api/v3/activities"
    headers = {"Authorization": f"Bearer {access_token}"}
    
    activity_data = {
        "name": metadata["name"],
        "type": metadata["type"],
        "distance": metadata["distance"],
        "elapsed_time": metadata["elapsed_time"],
        "description": metadata.get("description", ""),
        "trainer": metadata.get("trainer", 0),
        "commute": metadata.get("commute", 0)
    }

    response = requests.post(url, headers=headers, data=activity_data)

    if response.status_code == 201:
        print(f"New activity created successfully: {response.json()['id']}")
    else:
        print("Failed to create activity:", response.json())


def upload_tcx(access_token, file_path, activity_name="Trimmed Activity"):
    url = "https://www.strava.com/api/v3/uploads"
    headers = {"Authorization": f"Bearer {access_token}"}

    files = {
        "file": open(file_path, "rb"),
        "name": (None, activity_name),
        "description": (None, "This is a trimmed activity"),
        "data_type": (None, "tcx"),  # Can also be "gpx" or "fit"
    }

    response = requests.post(url, headers=headers, files=files)

    if response.status_code == 201:
        upload_id = response.json().get("id")
        print(f"File uploaded successfully. Upload ID: {upload_id}")
        return upload_id
    else:
        print("Failed to upload file:", response.json())
        return None

def check_upload_status(access_token, upload_id):
    url = f"https://www.strava.com/api/v3/uploads/{upload_id}"
    headers = {"Authorization": f"Bearer {access_token}"}

    while True:
        response = requests.get(url, headers=headers)
        data = response.json()

        if data.get("error"):
            print("Upload failed:", data["error"])
            return None

        status = data.get("status")
        if "Your activity is ready" in status:
            print("Activity successfully created:", data.get("activity_id"))
            return data.get("activity_id")

        print("Waiting for upload to process...")
        time.sleep(5)  # Wait 5 seconds before checking again

