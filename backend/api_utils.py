import os 
import json
import time
import requests
import logging
from dotenv import load_dotenv

load_dotenv()

# Load environment variables for backup use
CLIENT_ID = os.getenv("STRAVA_CLIENT_ID")
CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET")
REFRESH_TOKEN = os.getenv("STRAVA_REFRESH_TOKEN")

def get_access_token():
    """
    Get a new access token using the refresh token.
    
    Returns:
        str: A valid access token for Strava API
    """
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
        raise Exception(f"Error receiving access token: {data}")
    
    access_token = data["access_token"]
    logging.info(f"New access token generated (masked: ...{access_token[-4:]})")
    return access_token

def make_activity_private(activity_id, token, new_name=None):
    """
    Change an activity's visibility to private and optionally rename it.
    
    Args:
        activity_id (str): Strava activity ID
        token (str): Strava access token
        new_name (str, optional): New name for the activity
        
    Returns:
        bool: True if successful, False otherwise
    """
    import requests
    import logging
    import json
    
    logger = logging.getLogger(__name__)
    
    try:
        # Ensure activity_id is a string
        activity_id = str(activity_id)
        
        # Log important details (but mask part of the token)
        masked_token = token[:10] + "..." + token[-5:] if len(token) > 15 else "***"
        logger.info(f"Making activity {activity_id} private with token {masked_token}")
        
        # Construct the update URL
        url = f"https://www.strava.com/api/v3/activities/{activity_id}"
        
        # Set up headers with the authorization token
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        # Payload with private flag set to true
        payload = {
            "private": True
        }
        
        # Add new name if provided
        if new_name:
            payload["name"] = new_name
            logger.info(f"Renaming activity to: {new_name}")
        
        # Log the request details
        logger.info(f"Making PUT request to URL: {url} with payload: {payload}")
        
        # Send the update request
        response = requests.put(url, headers=headers, data=json.dumps(payload))
        
        # Check if the request was successful
        if response.status_code == 200:
            logger.info(f"Successfully made activity {activity_id} private")
            return True
        else:
            logger.error(f"Failed to make activity {activity_id} private: {response.status_code}")
            # Try to log response text if available
            try:
                error_detail = response.json()
                logger.error(f"Error details: {error_detail}")
            except:
                logger.error(f"Response text: {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"Exception in make_activity_private: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return False
    
def get_activity_details(activity_id, access_token):
    """
    Get details of a specific activity.
    
    Args:
        activity_id (str): ID of the activity to get details for
        access_token (str): Valid Strava access token
        
    Returns:
        dict: Activity data if successful, None otherwise
    """
    url = f"https://www.strava.com/api/v3/activities/{activity_id}"
    headers = {"Authorization": f"Bearer {access_token}"}

    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        activity_data = response.json()
        
        # Save the activity data to a file for debugging
        with open(f"activity_{activity_id}.json", "w") as f:
            json.dump(activity_data, f, indent=4)

        logging.info(f"Retrieved activity {activity_id} metadata")
        return activity_data
    else:
        logging.error(f"Failed to retrieve activity {activity_id}: {response.status_code}")
        return None

def create_activity(access_token, metadata):
    """
    Create a new activity on Strava.
    
    Args:
        access_token (str): Valid Strava access token
        metadata (dict): Activity metadata including name, type, distance, etc.
    
    Returns:
        str: New activity ID if successful, None otherwise
    """
    url = "https://www.strava.com/api/v3/activities"
    headers = {"Authorization": f"Bearer {access_token}"}
    
    # Prepare the activity data
    activity_data = {
        "name": metadata.get("name", "Trimmed Activity"),
        "type": metadata.get("type", "Run"),
        "start_date_local": metadata.get("start_date_local"),
        "elapsed_time": int(metadata.get("elapsed_time", 0)),
        "description": metadata.get("description", "Trimmed with Strim"),
        "distance": float(metadata.get("distance", 0)),
        "trainer": int(metadata.get("trainer", 0)),
        "commute": int(metadata.get("commute", 0))
    }
    
    # Add optional fields if available
    if "average_heartrate" in metadata:
        activity_data["average_heartrate"] = float(metadata["average_heartrate"])
    
    if "average_cadence" in metadata:
        activity_data["average_cadence"] = float(metadata["average_cadence"])
    
    if "average_speed" in metadata:
        activity_data["average_speed"] = float(metadata["average_speed"])

    # Log the data being sent (excluding sensitive info)
    logging.info(f"Creating activity with data: {activity_data}")
    
    response = requests.post(url, headers=headers, data=activity_data)

    if response.status_code in [200, 201]:
        new_activity_id = response.json().get('id')
        logging.info(f"New activity created successfully: {new_activity_id}")
        return new_activity_id
    else:
        logging.error(f"Failed to create activity: {response.status_code} {response.text}")
        return None

def upload_tcx(access_token, file_path, activity_name="Trimmed Activity"):
    """
    Upload a TCX file to Strava.
    
    Args:
        access_token (str): Valid Strava access token
        file_path (str): Path to the TCX file
        activity_name (str): Name for the new activity
    
    Returns:
        str: Upload ID if successful, None otherwise
    """
    url = "https://www.strava.com/api/v3/uploads"
    headers = {"Authorization": f"Bearer {access_token}"}

    # Ensure the file exists
    if not os.path.exists(file_path):
        logging.error(f"File not found: {file_path}")
        return None

    files = {
        "file": open(file_path, "rb"),
        "name": (None, activity_name),
        "description": (None, "Trimmed activity processed by Strim"),
        "data_type": (None, "tcx"),
    }

    try:
        response = requests.post(url, headers=headers, files=files)

        if response.status_code in [200, 201]:
            upload_data = response.json()
            upload_id = upload_data.get("id")
            logging.info(f"File uploaded successfully. Upload ID: {upload_id}")
            return upload_id
        else:
            logging.error(f"Failed to upload file: {response.status_code} {response.text}")
            return None
    except Exception as e:
        logging.error(f"Exception during upload: {str(e)}")
        return None
    finally:
        # Close the file to avoid resource leaks
        files["file"].close()

def check_upload_status(access_token, upload_id):
    """
    Check the status of an upload and wait for it to complete.
    
    Args:
        access_token (str): Valid Strava access token
        upload_id (str): ID of the upload to check
    
    Returns:
        str: New activity ID if successful, None otherwise
    """
    url = f"https://www.strava.com/api/v3/uploads/{upload_id}"
    headers = {"Authorization": f"Bearer {access_token}"}
    
    max_attempts = 30  # Maximum number of attempts to check status
    attempt = 0

    while attempt < max_attempts:
        attempt += 1
        try:
            response = requests.get(url, headers=headers)
            data = response.json()

            logging.info(f"Upload status check {attempt}: {data.get('status', 'unknown')}")

            if data.get("error"):
                logging.error(f"Upload failed: {data['error']}")
                return None

            status = data.get("status", "")
            
            # Check if upload is ready
            if "Your activity is ready" in status or data.get("activity_id"):
                activity_id = data.get("activity_id")
                logging.info(f"Activity successfully created: {activity_id}")
                return activity_id
                
            # Check if there's an error or if processing
            if "error" in status.lower():
                logging.error(f"Upload error: {status}")
                return None
                
            logging.info(f"Waiting for upload to process... Status: {status}")
            time.sleep(2)  # Wait 2 seconds before checking again
            
        except Exception as e:
            logging.error(f"Error checking upload status: {str(e)}")
            time.sleep(5)  # Wait longer on error
    
    logging.error(f"Upload processing timed out after {max_attempts} attempts")
    return None