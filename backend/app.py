from flask import Flask, request, redirect, jsonify, session, render_template, url_for
from flask_session import Session
from flask_cors import CORS
from flask_talisman import Talisman
from datetime import timedelta
import redis
import requests
import traceback
import logging
import time
import sys
import os
import urllib.parse  # Added for URL encoding

import api_utils
import trimmer

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Define base directories
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
)
logger = logging.getLogger(__name__)

app = Flask(
    __name__, 
    template_folder=os.path.join(FRONTEND_DIR, "templates"),  
    static_folder=os.path.join(FRONTEND_DIR, "static"),
    static_url_path="/static" 
)

# Production-only configuration
BASE_URL = "https://strim-production.up.railway.app"
FRONTEND_URL = "https://strimrun.vercel.app"

# Redis configuration
REDIS_URL = os.getenv("REDIS_URL")
if not REDIS_URL:
    logger.error("REDIS_URL not found in environment variables.")
    sys.exit(1)  # Exit if Redis URL is not set in production

# Try to establish Redis connection
try:
    redis_client = redis.from_url(REDIS_URL)
    redis_client.ping()
    logger.info("✅ Redis connection successful")
except (redis.exceptions.ConnectionError, redis.exceptions.RedisError) as e:
    logger.error(f"❌ Redis connection error: {str(e)}")
    logger.error("Exiting application due to Redis connection failure in production")
    sys.exit(1)

# Update the Flask session configuration
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY")
if not app.config["SECRET_KEY"]:
    logger.error("SECRET_KEY not found in environment variables.")
    sys.exit(1)  # Exit if secret key is not set in production
    
app.config["SESSION_TYPE"] = "redis"
app.config["SESSION_PERMANENT"] = True
app.config["SESSION_LIFETIME"] = timedelta(days=7)
app.config["SESSION_USE_SIGNER"] = True
app.config["SESSION_REDIS"] = redis_client

# Configure CORS to allow requests from frontend
cors = CORS()
cors.init_app(
    app,
    resources={r"/*": {
        "origins": [
            "https://strimrun.vercel.app",
            "https://strim-conner-groths-projects.vercel.app",
            "http://localhost:3000",
            "http://127.0.0.1:3000"
        ],
        "allow_headers": [
            "Content-Type", 
            "Authorization",
            "X-Requested-With", 
            "Accept", 
            "Origin", 
            "Cache-Control"  
        ],
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "expose_headers": ["Content-Type", "X-CSRFToken"],
        "supports_credentials": True
    }}
)

# Initialize Flask-Session
Session(app)

# Security Headers
Talisman(app, 
    content_security_policy={
        'default-src': "'self'",
        'script-src': "'self' 'unsafe-eval' https://cdnjs.cloudflare.com https://fonts.googleapis.com",
        'style-src': "'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://fonts.googleapis.com",
        'img-src': "'self' data:",
        'connect-src': "'self' https://www.strava.com",
        'font-src': "'self' https://fonts.gstatic.com",
    },
    force_https=True,
    frame_options='SAMEORIGIN',
    strict_transport_security=True,
    strict_transport_security_max_age=31536000,
    content_security_policy_nonce_in=['script-src'],
)

UPLOAD_FOLDER = "uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Simplified token extraction - focus on query parameters and headers
def get_token_from_request():
    """Extract the token from request, prioritizing query parameters."""
    # Check query parameters first (primary method)
    token = request.args.get('token')
    if token:
        app.logger.info("✅ Using token from query parameter")
        return token
    
    # Check Authorization header as fallback
    auth_header = request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        token = auth_header.split(' ')[1]
        app.logger.info("✅ Using token from Authorization header")
        return token
    
    # Check session as last resort
    if "strava_token" in session:
        token = session["strava_token"]
        app.logger.info("✅ Using token from session")
        return token
    
    return None

# ---------------- ROUTES ----------------

@app.route("/")
def home():
    """Render the main page."""
    return render_template("index.html")

@app.route("/auth")
def strava_auth():
    """Redirect user to Strava OAuth login page."""
    # Validate required environment variables
    client_id = os.getenv('STRAVA_CLIENT_ID')
    redirect_uri = os.getenv('STRAVA_REDIRECT_URI')
    
    if not client_id:
        app.logger.error("❌ STRAVA_CLIENT_ID environment variable is missing")
        return redirect(f"{FRONTEND_URL}?auth_error=missing_client_id")
        
    if not redirect_uri:
        app.logger.error("❌ STRAVA_REDIRECT_URI environment variable is missing")
        return redirect(f"{FRONTEND_URL}?auth_error=missing_redirect_uri")
    
    # Log the authentication attempt (mask part of client ID)
    masked_client_id = f"{client_id[:2]}...{client_id[-2:]}" if len(client_id) > 4 else "***"
    app.logger.info(f"🔑 Initiating Strava authentication with client ID: {masked_client_id}")
    app.logger.info(f"🔑 Using redirect URI: {redirect_uri}")
    
    # Build the authorization URL
    auth_url = (
        f"https://www.strava.com/oauth/authorize"
        f"?client_id={client_id}"
        f"&response_type=code"
        f"&redirect_uri={redirect_uri}"
        f"&scope=activity:read,activity:read_all,activity:write"
        f"&approval_prompt=auto"  # Only prompt for approval if the user hasn't already approved
    )
    
    app.logger.info(f"🔀 Redirecting to Strava authorization: {auth_url}")
    return redirect(auth_url)

@app.route("/auth/callback", methods=["GET"])
def strava_callback():
    """Handle Strava OAuth callback and redirect to frontend with token."""
    code = request.args.get("code")
    error = request.args.get("error")
    
    # Check for error parameter from Strava
    if error:
        app.logger.error(f"Strava returned an error: {error}")
        return redirect(f"{FRONTEND_URL}?auth_error={error}")
    
    if not code:
        app.logger.error("Missing authorization code in callback")
        return redirect(f"{FRONTEND_URL}?auth_error=missing_code")

    token_url = "https://www.strava.com/oauth/token"
    payload = {
        "client_id": os.getenv('STRAVA_CLIENT_ID'),
        "client_secret": os.getenv('STRAVA_CLIENT_SECRET'),
        "code": code,
        "grant_type": "authorization_code"
    }

    # Check if required environment variables are set
    if not os.getenv('STRAVA_CLIENT_ID'):
        app.logger.error("❌ STRAVA_CLIENT_ID environment variable is missing")
        return redirect(f"{FRONTEND_URL}?auth_error=missing_client_id")
        
    if not os.getenv('STRAVA_CLIENT_SECRET'):
        app.logger.error("❌ STRAVA_CLIENT_SECRET environment variable is missing")
        return redirect(f"{FRONTEND_URL}?auth_error=missing_client_secret")
    
    app.logger.info(f"📡 Sending token request to Strava")
    try:
        response = requests.post(token_url, data=payload, timeout=10)
        app.logger.info(f"🔄 Strava token response status: {response.status_code}")
        
        if response.status_code != 200:
            app.logger.error(f"❌ Strava token request failed with status {response.status_code}: {response.text}")
            return redirect(f"{FRONTEND_URL}?auth_error=strava_api_error&status={response.status_code}")
            
        token_data = response.json()
        
        # Log token data but mask sensitive info
        safe_log_data = {k: (v if k not in ['access_token', 'refresh_token'] else '***MASKED***') 
                          for k, v in token_data.items()}
        app.logger.info(f"🔄 Strava Response: {safe_log_data}")

        if "access_token" not in token_data:
            app.logger.error(f"❌ No access token in Strava response: {safe_log_data}")
            return redirect(f"{FRONTEND_URL}?auth_error=missing_access_token")

        # Save token data in session as backup
        session["strava_token"] = token_data["access_token"]
        session["refresh_token"] = token_data.get("refresh_token")
        session["expires_at"] = token_data.get("expires_at")
        session["athlete"] = token_data.get("athlete")
        session.modified = True
        
        # Include token in redirect to frontend
        token = token_data["access_token"]
        encoded_token = urllib.parse.quote(token)
        redirect_url = f"{FRONTEND_URL}?auth_success=true&token={encoded_token}"
        
        # Log the redirect URL (mask the token)
        masked_redirect = redirect_url.replace(encoded_token, "***MASKED***")
        app.logger.info(f"🔀 Redirecting to: {masked_redirect}")
        
        return redirect(redirect_url)
    except Exception as e:
        app.logger.error(f"❌ Error in Strava callback: {str(e)}")
        app.logger.error(traceback.format_exc())
        return redirect(f"{FRONTEND_URL}?auth_error=unexpected_error&message={str(e)}")

@app.route("/api/session-status")
def session_status():
    """Check if user has a valid token."""
    app.logger.info(f"📝 Session data: {dict(session)}")
    app.logger.info(f"🍪 Request cookies: {request.cookies}")
    
    # Get token using helper function
    token = get_token_from_request()
    
    if token:
        # Extract athlete info if in session
        athlete = session.get("athlete") if "athlete" in session else None
        expires_at = session.get("expires_at") if "expires_at" in session else None
        
        return jsonify({
            "authenticated": True,
            "athlete": athlete,
            "expires_at": expires_at,
            "token": token  # Include token in response
        })
    else:
        return jsonify({"authenticated": False, "reason": "no_token"})

@app.route("/activities", methods=["GET"])
def get_activities():
    """Retrieve user activities from Strava API."""
    app.logger.info(f"📝 Request to /activities - Session data: {dict(session)}")
    app.logger.info(f"🍪 Request cookies: {request.cookies}")
    app.logger.info(f"🔑 Auth header: {request.headers.get('Authorization')}")
    app.logger.info(f"🔑 Query params: {dict(request.args)}")
    
    # Get token using helper function
    token = get_token_from_request()
    
    # If no token, return unauthorized
    if not token:
        app.logger.error("❌ No valid token found")
        return jsonify({"error": "Unauthorized. No valid token."}), 401

    # Get activities from Strava
    url = "https://www.strava.com/api/v3/athlete/activities"
    headers = {"Authorization": f"Bearer {token}"}

    app.logger.info(f"📡 Sending request to Strava API")
    response = requests.get(url, headers=headers)
    
    if response.status_code != 200:
        app.logger.error(f"❌ Strava API error: {response.status_code} - {response.text}")
        return jsonify({"error": "Failed to fetch activities from Strava"}), response.status_code

    activities = response.json()
    app.logger.info(f"✅ Received {len(activities)} activities from Strava")
    
    # Include the token in the response for stateless clients
    return jsonify({
        "activities": [
            {
                "id": act["id"],
                "name": act["name"],
                "distance_miles": round(act["distance"] / 1609.34, 2),
                "date": act["start_date_local"]
            }
            for act in activities if act["type"] == "Run"
        ],
        "token": token  # Include token in response
    })

@app.route("/trim-activity", methods=["GET"])
def trim_activity():
    """Process and trim a Strava activity using stream data."""
    try:
        # Get token from request
        token = get_token_from_request()
        
        if not token:
            return jsonify({"error": "Authentication required"}), 401
            
        # Get parameters from request
        activity_id = request.args.get("activity_id")
        edit_distance = request.args.get("edit_distance") == "true"
        new_distance = None
        
        # Get manual trim points if provided
        trim_start_time = request.args.get("trim_start_time")
        trim_end_time = request.args.get("trim_end_time")
        manual_trim_points = None
        
        if trim_start_time is not None and trim_end_time is not None:
            try:
                # Convert to integers
                trim_start_time = int(float(trim_start_time))
                trim_end_time = int(float(trim_end_time))
                
                # Create manual trim points object
                manual_trim_points = {
                    'start_time': trim_start_time,
                    'end_time': trim_end_time
                }
                
                app.logger.info(f"Using manual trim points: {manual_trim_points}")
            except (ValueError, TypeError) as e:
                app.logger.error(f"Error parsing manual trim points: {str(e)}")
                return jsonify({"error": f"Invalid trim points: {str(e)}"}), 400
        
        if edit_distance:
            try:
                new_distance = float(request.args.get("new_distance")) * 1609.34  # Convert miles to meters
                app.logger.info(f"User provided new distance: {new_distance} meters")
            except (ValueError, TypeError) as e:
                return jsonify({"error": f"Invalid distance value: {str(e)}"}), 400

        if not activity_id:
            return jsonify({"error": "Activity ID is required"}), 400
            
        # 1. Get activity details and streams from Strava
        app.logger.info(f"Getting activity details for {activity_id}")
        activity_metadata = api_utils.get_activity_details(activity_id, token)
        
        if not activity_metadata:
            return jsonify({"error": "Failed to retrieve activity details from Strava"}), 500
            
        # Get streams data for trimming
        app.logger.info(f"Getting activity streams for {activity_id}")
        streams_url = f"https://www.strava.com/api/v3/activities/{activity_id}/streams"
        headers = {"Authorization": f"Bearer {token}"}
        params = {
            "keys": "time,distance,velocity_smooth,heartrate,altitude,cadence",
            "key_by_type": "true"
        }
        
        streams_response = requests.get(streams_url, headers=headers, params=params)
        if streams_response.status_code != 200:
            app.logger.error(f"Failed to get streams: {streams_response.status_code} {streams_response.text}")
            return jsonify({"error": "Failed to retrieve activity streams from Strava"}), 500
            
        stream_data = streams_response.json()
        
        # 2. Process the activity with manual trim points and/or corrected distance
        app.logger.info(f"Processing activity {activity_id} with trimmer")
        options = {}
        if manual_trim_points:
            options['manual_trim_points'] = manual_trim_points
            
        try:
            # Use the trimmer module to process the activity
            trimmed_metrics = trimmer.estimate_trimmed_activity_metrics(
                activity_id, 
                stream_data, 
                activity_metadata, 
                corrected_distance=new_distance,
                options=options
            )
            
            if not trimmed_metrics:
                return jsonify({"error": "Failed to process activity metrics"}), 500
                
        except Exception as e:
            app.logger.error(f"Error in trimmer: {str(e)}")
            tb = traceback.format_exc()
            app.logger.error(tb)
            return jsonify({
                "error": f"Error processing activity data: {str(e)}",
                "traceback": tb
            }), 500
        
        # 3. Mark the original activity (if needed)
        if manual_trim_points or edit_distance:
            try:
                app.logger.info(f"Modifying original activity {activity_id}")
                modify_success = api_utils.modify_activity_aggressively(activity_id, token)
                if not modify_success:
                    app.logger.warning(f"Failed to modify original activity {activity_id}")
            except Exception as e:
                app.logger.warning(f"Error modifying original activity: {str(e)}")
        
        # 4. Create a new activity with the processed metrics
        app.logger.info(f"Creating new activity from processed metrics")
        new_activity_id = api_utils.create_activity(token, trimmed_metrics)
        
        if not new_activity_id:
            return jsonify({"error": "Failed to create new activity"}), 500
            
        app.logger.info(f"Successfully created new activity: {new_activity_id}")
        
        # 5. Mark the original activity as archived (if needed)
        if manual_trim_points or edit_distance:
            try:
                app.logger.info(f"Marking original activity {activity_id} as archived")
                api_utils.mark_original_activity(
                    activity_id, 
                    token, 
                    activity_metadata.get("name", "Activity"), 
                    new_activity_id
                )
            except Exception as e:
                app.logger.warning(f"Error marking original activity: {str(e)}")
        
        # Return success with the new activity ID
        return jsonify({
            "success": True,
            "new_activity_id": new_activity_id,
            "original_activity_id": activity_id,
            "new_distance": trimmed_metrics.get("distance"),
            "new_time": trimmed_metrics.get("elapsed_time"),
            "new_pace": (trimmed_metrics.get("elapsed_time") / trimmed_metrics.get("distance")) if trimmed_metrics.get("distance") else 0,
            "token": token
        })
        
    except Exception as e:
        app.logger.error(f"Error processing activity: {str(e)}")
        tb = traceback.format_exc()
        app.logger.error(tb)
        return jsonify({
            "error": f"Error processing activity: {str(e)}",
            "traceback": tb
        }), 500

@app.route("/update-distance", methods=["POST"])
def update_distance():
    """Update activity distance and re-upload to Strava."""
    # Get token using helper function
    token = get_token_from_request()
    
    # If no token, return unauthorized
    if not token:
        app.logger.error("❌ No valid token found for update-distance")
        return jsonify({"error": "Unauthorized. No valid token."}), 401

    data = request.json
    activity_id = data.get("activity_id")
    new_distance = data.get("new_distance")

    if not activity_id or not new_distance:
        return jsonify({"error": "Missing required data"}), 400

    # Fetch existing activity details
    activity_metadata = api_utils.get_activity_details(activity_id, token)
    if not activity_metadata:
        return jsonify({"error": "Failed to fetch activity details"}), 500

    # Update metadata with new distance
    activity_metadata["distance"] = float(new_distance)

    # Delete original activity
    delete_success = api_utils.delete_activity(activity_id, token)
    if not delete_success:
        return jsonify({"error": "Failed to delete original activity"}), 500

    # Recreate activity with updated distance
    new_activity_id = api_utils.create_activity(token, activity_metadata)
    if not new_activity_id:
        return jsonify({"error": "Failed to create new activity"}), 500

    return jsonify({
        "success": True, 
        "new_activity_id": new_activity_id,
        "token": token
    })

@app.route("/activities/<activity_id>/details", methods=["GET"])
def get_activity_details(activity_id):
    try:
        # Get token using helper function
        token = get_token_from_request()
        
        # If no token, return unauthorized
        if not token:
            app.logger.error("❌ No valid token found for activity details")
            return jsonify({"error": "Unauthorized. No valid token."}), 401

        # Get activity details from Strava
        activity_metadata = api_utils.get_activity_details(activity_id, token)
        
        if not activity_metadata:
            return jsonify({"error": "Failed to retrieve activity details"}), 404
            
        return jsonify(activity_metadata)
    except Exception as e:
        app.logger.error(f"Error retrieving activity details: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/restore-activity", methods=["GET"])
def restore_activity():
    """Restore an original activity by making it public again and optionally delete the trimmed one."""
    try:
        # Get token from request
        token = get_token_from_request()
        
        if not token:
            return jsonify({"error": "Authentication required"}), 401
            
        # Get parameters from request
        original_activity_id = request.args.get("original_activity_id")
        new_activity_id = request.args.get("new_activity_id")
        delete_new = request.args.get("delete_new", "false") == "true"
        
        if not original_activity_id:
            return jsonify({"error": "Original activity ID is required"}), 400
        
        # Get original activity details
        app.logger.info(f"Getting details for original activity {original_activity_id}")
        original_activity = api_utils.get_activity_details(original_activity_id, token)
        
        if not original_activity:
            return jsonify({"error": "Failed to retrieve original activity details"}), 404
        
        # Restore the original activity
        app.logger.info(f"Restoring original activity {original_activity_id}")
        
        # Extract original name (remove [ARCHIVED] prefix if it exists)
        original_name = original_activity.get("name", "Activity")
        if original_name.startswith("[ARCHIVED] "):
            original_name = original_name[11:]  # Remove the prefix
        
        # Generate a unique timestamp and random suffix to avoid duplicate detection
        import time
        import random
        import string
        
        timestamp = int(time.time())
        random_suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        
        # Create a new unique name to avoid duplicate detection
        restored_name = f"{original_name} (Restored {timestamp}-{random_suffix})"
        
        app.logger.info(f"Changing activity name to: {restored_name}")
        
        # Prepare the payload to update the original activity
        restore_payload = {
            "name": restored_name,
            "description": original_activity.get("description", ""),
            "private": False,  # Make the activity public again
            "type": original_activity.get("type", "Run"),  # Ensure the type is correct
        }
        
        # Update the original activity
        restore_url = f"https://www.strava.com/api/v3/activities/{original_activity_id}"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        
        app.logger.info(f"Updating original activity {original_activity_id}")
        restore_response = requests.put(restore_url, headers=headers, json=restore_payload)
        
        if restore_response.status_code != 200:
            app.logger.error(f"Failed to restore original activity: {restore_response.status_code} {restore_response.text}")
            return jsonify({"error": "Failed to restore original activity"}), 500
        
        # Optionally delete the new trimmed activity
        delete_result = True
        if delete_new and new_activity_id:
            app.logger.info(f"Deleting trimmed activity {new_activity_id}")
            delete_result = api_utils.delete_activity(new_activity_id, token)
            
            if not delete_result:
                app.logger.warning(f"Failed to delete trimmed activity {new_activity_id}")
        
        # Now that restoration succeeded with a temporary name, let's update it back to the original name
        # This second update should work because we've already changed it enough to avoid duplicate detection
        time.sleep(1)  # Short delay to ensure the first update completes
        
        final_name_payload = {
            "name": original_name
        }
        
        app.logger.info(f"Updating activity name back to original: {original_name}")
        final_update_response = requests.put(restore_url, headers=headers, json=final_name_payload)
        
        if final_update_response.status_code != 200:
            app.logger.warning(f"Failed to restore original name: {final_update_response.status_code} {final_update_response.text}")
            # This is not critical, so we'll continue and return success anyway
        
        return jsonify({
            "success": True,
            "original_activity_id": original_activity_id,
            "new_activity_deleted": delete_new and delete_result,
            "token": token
        })
        
    except Exception as e:
        app.logger.error(f"Error restoring activity: {str(e)}")
        tb = traceback.format_exc()
        app.logger.error(tb)
        return jsonify({
            "error": f"Error restoring activity: {str(e)}",
            "traceback": tb
        }), 500

@app.route("/logout", methods=["POST"])
def logout():
    """Clear user session."""
    session.clear()
    return jsonify({"success": True})

@app.route("/api/ping", methods=["GET", "OPTIONS"])
def ping():
    """Simple endpoint to check if the API is accessible."""
    return jsonify({
        "status": "ok", 
        "message": "API is accessible"
    }), 200

@app.after_request
def log_response_headers(response):
    """Log response headers and ensure CORS is properly set."""
    app.logger.debug(f"Response Headers: {dict(response.headers)}")
    
    # Set CORS headers for cross-domain requests
    origin = request.headers.get('Origin')
    allowed_origins = [
        "https://strimrun.vercel.app",
        "https://strim-conner-groths-projects.vercel.app",
        "http://localhost:3000",
        "http://127.0.0.1:3000"
    ]
    
    if origin in allowed_origins:
        response.headers.add('Access-Control-Allow-Origin', origin)
        response.headers.add('Access-Control-Allow-Headers', 
                            'Content-Type,Authorization,X-Requested-With,Accept,Origin,Cache-Control')
        response.headers.add('Access-Control-Allow-Methods', 'GET,POST,PUT,DELETE,OPTIONS')
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        
    # Handle preflight OPTIONS requests
    if request.method == 'OPTIONS':
        response.status_code = 200
        return response
        
    return response

@app.context_processor
def inject_env_variables():
    return {
        "BASE_URL": BASE_URL,
        "FRONTEND_URL": FRONTEND_URL,
        "ENVIRONMENT": "production"
    }

@app.route("/api/check-env", methods=["GET"])
def check_env():
    """Check environment variables (admin only)."""
    # This should only be accessible with an admin token in production
    admin_token = request.args.get('admin_token')
    if not admin_token or admin_token != os.getenv('ADMIN_SECRET'):
        return jsonify({"error": "Unauthorized"}), 401
        
    # Check critical environment variables
    env_status = {
        "STRAVA_CLIENT_ID": bool(os.getenv('STRAVA_CLIENT_ID')),
        "STRAVA_CLIENT_SECRET": bool(os.getenv('STRAVA_CLIENT_SECRET')),
        "STRAVA_REDIRECT_URI": os.getenv('STRAVA_REDIRECT_URI'),
        "FLASK_SECRET_KEY": bool(os.getenv('FLASK_SECRET_KEY')),
        "REDIS_URL": bool(os.getenv('REDIS_URL')),
        "BASE_URL": BASE_URL,
        "FRONTEND_URL": FRONTEND_URL
    }
    
    # Check Redis connection
    try:
        redis_client.ping()
        env_status["REDIS_CONNECTION"] = "OK"
    except Exception as e:
        env_status["REDIS_CONNECTION"] = f"ERROR: {str(e)}"
    
    return jsonify(env_status)

@app.route("/activity-streams", methods=["GET"])
def get_activity_streams():
    """
    Retrieve specific activity streams for visualization.
    Params:
        - activity_id: ID of the activity
        - token: Strava API token
    Returns:
        JSON with streams data formatted for visualization
    """
    activity_id = request.args.get("activity_id")
    token = request.args.get("token")
    
    if not activity_id or not token:
        return jsonify({"error": "Missing required parameters"}), 400
    
    # Request streams from Strava
    streams_url = f"https://www.strava.com/api/v3/activities/{activity_id}/streams"
    headers = {"Authorization": f"Bearer {token}"}
    params = {
        # Request specific streams needed for visualization
        "keys": "time,distance,velocity_smooth,heartrate,altitude",
        "key_by_type": "true"
    }
    
    try:
        app.logger.info(f"Requesting streams for visualization: {activity_id}")
        response = requests.get(streams_url, headers=headers, params=params)
        
        if response.status_code != 200:
            app.logger.error(f"Failed to get activity streams: {response.status_code} {response.text}")
            return jsonify({"error": "Failed to retrieve activity streams from Strava"}), 500
            
        # Get activity metadata for additional context
        activity_url = f"https://www.strava.com/api/v3/activities/{activity_id}"
        activity_response = requests.get(activity_url, headers=headers)
        
        if activity_response.status_code != 200:
            app.logger.warning(f"Failed to get activity metadata: {activity_response.status_code}")
            activity_metadata = {}
        else:
            activity_metadata = activity_response.json()
            
        # Parse the stream data
        stream_data = response.json()
        
        # Process the streams data for visualization
        viz_data = format_streams_for_visualization(stream_data, activity_metadata)
        
        return jsonify(viz_data)
        
    except Exception as e:
        app.logger.error(f"Error retrieving activity streams: {str(e)}")
        app.logger.error(traceback.format_exc())
        return jsonify({"error": f"Error: {str(e)}"}), 500

def format_streams_for_visualization(stream_data, activity_metadata):
    """
    Format the streams data for visualization in the frontend.
    
    Args:
        stream_data (dict): Stream data from Strava API
        activity_metadata (dict): Activity metadata
        
    Returns:
        dict: Formatted data for visualization
    """
    # Get measurement preferences (metric or imperial)
    is_metric = activity_metadata.get("measurement_preference", "meters") == "meters"
    
    # Prepare the base response
    response = {
        "activity": {
            "id": activity_metadata.get("id", ""),
            "name": activity_metadata.get("name", "Activity"),
            "type": activity_metadata.get("type", "Run"),
            "start_date": activity_metadata.get("start_date_local", ""),
            "distance": activity_metadata.get("distance", 0),
            "elapsed_time": activity_metadata.get("elapsed_time", 0),
            "moving_time": activity_metadata.get("moving_time", 0),
            "is_metric": is_metric
        },
        "streams": {},
        "pace_data": [],
        "elevation_data": []
    }
    
    # Check if we have the required streams
    has_time = "time" in stream_data
    has_distance = "distance" in stream_data
    has_velocity = "velocity_smooth" in stream_data
    has_altitude = "altitude" in stream_data
    
    if not (has_time and has_distance):
        app.logger.warning("Missing required streams (time or distance)")
        return {"error": "Missing required stream data"}
    
    # Extract time and distance streams
    time_stream = stream_data.get("time", {}).get("data", [])
    distance_stream = stream_data.get("distance", {}).get("data", [])
    
    # Basic validation - ensure same length
    if len(time_stream) != len(distance_stream):
        app.logger.warning(f"Stream length mismatch: time={len(time_stream)}, distance={len(distance_stream)}")
        # Trim to the shorter length
        min_length = min(len(time_stream), len(distance_stream))
        time_stream = time_stream[:min_length]
        distance_stream = distance_stream[:min_length]
    
    # Calculate pace data (time per distance unit)
    pace_data = []
    if has_velocity:
        velocity_stream = stream_data.get("velocity_smooth", {}).get("data", [])
        
        # Trim velocity stream to match time/distance
        velocity_stream = velocity_stream[:min(len(velocity_stream), len(time_stream))]
        
        for i in range(len(time_stream)):
            time_seconds = time_stream[i]
            distance_meters = distance_stream[i]
            
            # Convert meters to miles/km based on user preference
            if is_metric:
                distance_km = distance_meters / 1000
                distance_formatted = f"{distance_km:.2f} km"
            else:
                distance_miles = distance_meters / 1609.34
                distance_formatted = f"{distance_miles:.2f} mi"
            
            # Calculate pace from velocity (m/s)
            if i < len(velocity_stream) and velocity_stream[i] > 0:
                velocity = velocity_stream[i]  # in m/s
                
                # Convert to pace (time per distance)
                if is_metric:
                    # min/km
                    pace_seconds_per_km = 1000 / velocity
                    pace_minutes = pace_seconds_per_km / 60
                    pace_formatted = f"{int(pace_minutes)}:{int((pace_minutes % 1) * 60):02d}"
                else:
                    # min/mile
                    pace_seconds_per_mile = 1609.34 / velocity
                    pace_minutes = pace_seconds_per_mile / 60
                    pace_formatted = f"{int(pace_minutes)}:{int((pace_minutes % 1) * 60):02d}"
            else:
                pace_formatted = "0:00"
                velocity = 0
            
            # Calculate elapsed time in minutes for visualization
            minutes_elapsed = time_seconds / 60
            
            pace_data.append({
                "time": time_seconds,
                "minutes": minutes_elapsed,
                "distance": distance_meters,
                "distance_formatted": distance_formatted,
                "velocity": velocity,
                "pace": pace_formatted
            })
    
    # Add elevation data if available
    elevation_data = []
    if has_altitude:
        altitude_stream = stream_data.get("altitude", {}).get("data", [])
        
        # Trim to match time stream
        altitude_stream = altitude_stream[:min(len(altitude_stream), len(time_stream))]
        
        for i in range(len(time_stream)):
            if i < len(altitude_stream):
                elevation_data.append({
                    "time": time_stream[i],
                    "minutes": time_stream[i] / 60,
                    "altitude": altitude_stream[i]
                })
    
    # Calculate summary metrics
    if has_velocity and len(velocity_stream) > 0:
        avg_velocity = sum(velocity_stream) / len(velocity_stream)
        
        # Calculate average pace
        if is_metric:
            # min/km
            avg_pace_seconds_per_km = 1000 / avg_velocity
            avg_pace_minutes = avg_pace_seconds_per_km / 60
            avg_pace = f"{int(avg_pace_minutes)}:{int((avg_pace_minutes % 1) * 60):02d}"
        else:
            # min/mile
            avg_pace_seconds_per_mile = 1609.34 / avg_velocity
            avg_pace_minutes = avg_pace_seconds_per_mile / 60
            avg_pace = f"{int(avg_pace_minutes)}:{int((avg_pace_minutes % 1) * 60):02d}"
            
        response["activity"]["average_pace"] = avg_pace
        response["activity"]["average_speed"] = avg_velocity
    
    # Add the processed data to the response
    response["pace_data"] = pace_data
    response["elevation_data"] = elevation_data
    
    return response

@app.route("/download-fit", methods=["GET"])
def download_fit_legacy():
    """Legacy endpoint for backward compatibility - redirects to trim-activity."""
    app.logger.info("Legacy /download-fit endpoint accessed - redirecting to /trim-activity")
    return trim_activity()

# ---------------- END ROUTES ----------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

def create_app():
    return app