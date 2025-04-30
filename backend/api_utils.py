import os 
import json
import time
import requests
import logging
import random
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

def modify_activity_aggressively(activity_id, token):
    """
    Aggressively modify an activity's metadata to avoid duplicate detection.
    Changes activity type and name to make it clearly different.
    
    Args:
        activity_id (str): Strava activity ID
        token (str): Strava access token
        
    Returns:
        bool: True if successful, False otherwise
    """
    import requests
    import logging
    import json
    import time
    import random
    import string
    
    logger = logging.getLogger(__name__)
    
    try:
        # Prepare the request URL
        url = f"https://www.strava.com/api/v3/activities/{activity_id}"
        
        # Set up headers
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        # Get current activity details
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            logger.error(f"Failed to get activity details: {response.status_code}")
            return False
            
        activity = response.json()
        original_type = activity.get("type", "Run")
        timestamp = int(time.time())
        random_str = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        
        # Create a completely different name using a timestamp and random string
        new_name = f"TEMP_{timestamp}_{random_str}"
        
        # Choose a different activity type
        activity_types = ["Workout", "Walk", "Hike", "VirtualRide", "Yoga"]
        if original_type in activity_types:
            activity_types.remove(original_type)
        new_type = random.choice(activity_types)
        
        # Prepare the payload with significant changes
        payload = {
            "name": new_name,
            "type": new_type,
            "private": True,
            "sport_type": new_type  # Also change sport_type if it exists
        }
        
        logger.info(f"Aggressively modifying activity {activity_id}")
        logger.info(f"New name: {new_name}, New type: {new_type}")
        
        # Send the update request
        update_response = requests.put(url, headers=headers, json=payload)
        
        if update_response.status_code == 200:
            logger.info(f"Successfully modified activity {activity_id}")
            return True
        else:
            logger.error(f"Failed to modify activity: {update_response.status_code} {update_response.text}")
            return False
            
    except Exception as e:
        logger.error(f"Error modifying activity: {str(e)}")
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

def cleanup_activity(activity_id, token, original_name, original_description=None):
    """
    Clean up the activity by restoring original name and description.
    
    Args:
        activity_id (str): Strava activity ID
        token (str): Strava access token
        original_name (str): Original activity name to restore
        original_description (str, optional): Original description to restore
        
    Returns:
        bool: True if successful, False otherwise
    """
    import requests
    import logging
    import json
    
    logger = logging.getLogger(__name__)
    
    try:
        # Prepare the request URL
        url = f"https://www.strava.com/api/v3/activities/{activity_id}"
        
        # Set up headers
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        # Prepare the payload with clean name
        payload = {
            "name": original_name
        }
        
        # Add description if provided
        if original_description is not None:
            payload["description"] = original_description
        
        logger.info(f"Cleaning up activity {activity_id} - restoring original name")
        
        # Send the update request
        response = requests.put(url, headers=headers, data=json.dumps(payload))
        
        # Check if the request was successful
        if response.status_code == 200:
            logger.info(f"Successfully cleaned up activity {activity_id}")
            return True
        else:
            logger.error(f"Failed to clean up activity: {response.status_code} {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"Error cleaning up activity: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return False

def mark_original_activity(activity_id, token, original_name, new_activity_id):
    """
    Mark the original activity as superseded by a trimmed version.
    
    Args:
        activity_id (str): Original activity ID
        token (str): Strava access token
        original_name (str): Original activity name
        new_activity_id (str): ID of the new trimmed activity, or "pending" if not yet created
        
    Returns:
        bool: True if successful, False otherwise
    """
    logger = logging.getLogger(__name__)
    
    try:
        # Prepare the request URL
        url = f"https://www.strava.com/api/v3/activities/{activity_id}"
        
        # Set up headers
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        # Generate unique identifiers to avoid duplicate detection when restoring
        import time
        import random
        import string
        
        timestamp = int(time.time())
        random_suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        
        # Create a unique name for the original activity to avoid duplicate detection
        # Don't include the original name to avoid potential duplicates with the trimmed copy
        new_name = f"ARCHIVED_COPY_{timestamp}_{random_suffix}"
        
        # Create a helpful description for the original activity
        if new_activity_id == "pending":
            # If the new activity hasn't been created yet, use a generic description
            description = (
                f"This is an archived copy of '{original_name}' that has been trimmed using Strim.\n\n"
                f"You can safely delete this archived copy once the new trimmed activity is created."
            )
        else:
            # Include a link to the new activity
            description = (
                f"This is an archived copy of '{original_name}' that has been trimmed using Strim.\n\n"
                f"A new version is available here: https://www.strava.com/activities/{new_activity_id}\n\n"
                f"You can safely delete this archived copy."
            )
        
        # Prepare the payload with a significantly altered name
        payload = {
            "name": new_name,
            "description": description,
            "private": True  # Mark as private to reduce clutter in feed
        }
        
        logger.info(f"Marking original activity {activity_id} as archived with name {new_name}")
        
        # Send the update request
        response = requests.put(url, headers=headers, json=payload)
        
        if response.status_code == 200:
            logger.info(f"Successfully marked original activity {activity_id} as archived")
            return True
        else:
            logger.error(f"Failed to mark original activity: {response.status_code} {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"Error marking original activity: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return False

def create_activity(token, activity_data):
    """
    Create a new activity on Strava.
    
    Args:
        token (str): Strava access token
        activity_data (dict): Activity details
        
    Returns:
        str: New activity ID if successful, None otherwise
    """
    import requests
    import logging
    import json
    from datetime import datetime
    import time
    import random
    import string
    
    logger = logging.getLogger(__name__)
    
    try:
        # Prepare the request URL
        url = "https://www.strava.com/api/v3/activities"
        
        # Set up headers
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        # Prepare the payload with required fields
        payload = {
            "name": activity_data.get("name", "Activity"),
            "type": activity_data.get("type", "Run"),
            "start_date_local": activity_data.get("start_date_local"),
            "elapsed_time": activity_data.get("elapsed_time", 0),
            "description": activity_data.get("description", ""),
            "distance": activity_data.get("distance", 0),
            # Convert boolean to integer for Strava API
            "trainer": 1 if activity_data.get("trainer", False) else 0,
            "commute": 1 if activity_data.get("commute", False) else 0
        }
        
        # Add optional fields if present
        if "private" in activity_data:
            payload["private"] = 1 if activity_data.get("private", False) else 0
            
        if "gear_id" in activity_data:
            payload["gear_id"] = activity_data.get("gear_id")
            
        # Add optional metrics if available
        for field in ["average_heartrate", "average_speed", "average_cadence"]:
            if field in activity_data:
                payload[field] = activity_data.get(field)
                
        # Handle start date format issues
        # If start_date_local is missing or malformed, use current time
        if not payload.get("start_date_local") or "Z" not in payload["start_date_local"]:
            # Create current time in ISO format
            current_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
            payload["start_date_local"] = current_time
            logger.warning(f"Using current time ({current_time}) for activity start_date_local")
        
        # Add jitter to start time to avoid conflict
        # This helps prevent 409 errors when creating multiple activities
        try:
            # Parse the start date
            start_date = datetime.strptime(payload["start_date_local"], "%Y-%m-%dT%H:%M:%SZ")
            # Add a few seconds of jitter
            jitter_seconds = int(time.time() % 60)  # Use seconds from current time
            new_start_date = start_date.replace(second=jitter_seconds)
            # Format back to string
            payload["start_date_local"] = new_start_date.strftime("%Y-%m-%dT%H:%M:%SZ")
            logger.info(f"Added jitter to start time: {payload['start_date_local']}")
        except Exception as e:
            logger.warning(f"Could not add jitter to start time: {str(e)}")
        
        # Log sanitized payload (for debugging)
        logger.info(f"Creating activity with data: {payload}")
        
        # Try to create the activity
        response = requests.post(url, headers=headers, json=payload)
        
        # If we get a 409 Conflict (duplicate detection), try again with a more unique name
        max_retries = 3
        retry_count = 0
        
        while response.status_code == 409 and retry_count < max_retries:
            retry_count += 1
            
            # Generate a more unique name with timestamp and random string
            timestamp = int(time.time())
            random_str = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
            original_name = payload["name"]
            payload["name"] = f"{original_name} ({timestamp}-{random_str})"
            
            # Also add more jitter to the start time
            try:
                start_date = datetime.strptime(payload["start_date_local"], "%Y-%m-%dT%H:%M:%SZ")
                new_jitter = random.randint(0, 59)
                new_start_date = start_date.replace(second=new_jitter)
                payload["start_date_local"] = new_start_date.strftime("%Y-%m-%dT%H:%M:%SZ")
            except Exception:
                pass
                
            logger.info(f"Retry {retry_count}: Creating activity with modified name: {payload['name']}")
            
            # Try again with the modified payload
            response = requests.post(url, headers=headers, json=payload)
        
        # Check if the request was successful
        if response.status_code == 201 or response.status_code == 200:
            # Extract the new activity ID from the response
            activity_data = response.json()
            new_activity_id = activity_data.get("id")
            
            if new_activity_id:
                logger.info(f"Successfully created activity {new_activity_id}")
                return str(new_activity_id)
            else:
                logger.error("Activity created but no ID returned")
                return None
        else:
            # Log the error
            logger.error(f"Failed to create activity: {response.status_code} {response.text}")
            
            # Provide more specific error messages based on status code
            if response.status_code == 400:
                logger.error("Bad request - check activity data format")
            elif response.status_code == 401:
                logger.error("Unauthorized - token may be invalid or expired")
            elif response.status_code == 403:
                logger.error("Forbidden - insufficient permissions")
            elif response.status_code == 409:
                logger.error("Conflict - activity may already exist with similar attributes")
                
            # Return failure
            return None
            
    except Exception as e:
        logger.error(f"Error creating activity: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
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

def delete_activity(activity_id, token):
    """
    Delete an activity from Strava.
    
    Args:
        activity_id (str): ID of the activity to delete
        token (str): Strava access token
        
    Returns:
        bool: True if successful, False otherwise
    """
    logger = logging.getLogger(__name__)
    
    try:
        url = f"https://www.strava.com/api/v3/activities/{activity_id}"
        headers = {"Authorization": f"Bearer {token}"}
        
        logger.info(f"Deleting activity {activity_id}")
        response = requests.delete(url, headers=headers)
        
        if response.status_code in [200, 204]:
            logger.info(f"Successfully deleted activity {activity_id}")
            return True
        else:
            logger.error(f"Failed to delete activity: {response.status_code} {response.text}")
            return False
    except Exception as e:
        logger.error(f"Error deleting activity: {str(e)}")
        return False