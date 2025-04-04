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
        "expose_headers": ["Content-Type", "X-CSRFToken"]
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

@app.route("/download-fit", methods=["GET"])
def download_fit():
    """Download activity data, modify old activity, and create new one with original time."""
    try:
        # Import necessary modules
        import json
        import time
        import random
        import datetime
        import traceback
        import requests
        
        # Get token using helper function
        token = get_token_from_request()
        
        # If no token, return unauthorized
        if not token:
            app.logger.error("❌ No valid token found for download-fit")
            return jsonify({"error": "Unauthorized. No valid token."}), 401

        activity_id = request.args.get("activity_id")
        edit_distance = request.args.get("edit_distance") == "true"
        new_distance = request.args.get("new_distance")

        if not activity_id:
            return jsonify({"error": "Missing activity ID"}), 400

        if edit_distance and (not new_distance or float(new_distance) <= 0):
            return jsonify({"error": "Invalid new distance provided"}), 400
            
        # Convert new_distance from miles to meters if editing distance
        corrected_distance = None
        if edit_distance and new_distance:
            # Convert miles to meters (1 mile = 1609.34 meters)
            corrected_distance = float(new_distance) * 1609.34
            app.logger.info(f"Converting {new_distance} miles to {corrected_distance} meters")

        app.logger.info(f"Processing activity {activity_id} (edit_distance={edit_distance}, new_distance={new_distance})")

        # Step 1: Get activity details
        activity_metadata = api_utils.get_activity_details(activity_id, token)
        if not activity_metadata:
            return jsonify({"error": "Failed to retrieve activity details"}), 500
            
        # Save the original activity attributes we want to preserve
        original_name = activity_metadata.get("name", "Activity")
        original_type = activity_metadata.get("type", "Run")
        original_date = activity_metadata.get("start_date_local")
        original_gear_id = activity_metadata.get("gear_id")
        
        app.logger.info(f"Retrieved activity metadata: {original_name}, " 
                      f"type: {original_type}, "
                      f"date: {original_date}, "
                      f"gear: {original_gear_id}")

        # Step 2: Get activity streams
        streams_url = f"https://www.strava.com/api/v3/activities/{activity_id}/streams"
        headers = {"Authorization": f"Bearer {token}"}
        params = {
            # Request specific streams
            "keys": "time,distance,latlng,altitude,velocity_smooth,heartrate,cadence,moving",
            # The key_by_type parameter affects the response format
            "key_by_type": "true" 
        }

        app.logger.info(f"Requesting streams from: {streams_url} with params: {params}")
        response = requests.get(streams_url, headers=headers, params=params)

        if response.status_code != 200:
            app.logger.error(f"Failed to get activity streams: {response.status_code} {response.text}")
            return jsonify({"error": "Failed to retrieve activity streams from Strava"}), 500

        # Get stream data
        stream_data = response.text
        
        # Step 3: Process streams to determine trim point and new metrics
        try:
            # Process the streams data
            trimmed_metrics = trimmer.estimate_trimmed_activity_metrics(
                activity_id, 
                stream_data, 
                activity_metadata,
                corrected_distance
            )
            
            if not trimmed_metrics:
                return jsonify({"error": "Failed to process activity streams"}), 500
                
            app.logger.info(f"Calculated trimmed metrics: {trimmed_metrics}")
        except Exception as e:
            app.logger.error(f"Error processing streams: {str(e)}")
            app.logger.error(traceback.format_exc())
            return jsonify({"error": f"Error processing activity: {str(e)}"}), 500

        # Step 4: Modify the original activity to avoid duplicate detection
        app.logger.info(f"Modifying original activity {activity_id} to avoid duplicate detection")
        
        # Parse the original time from the activity metadata
        original_time = None
        try:
            if original_date:
                # Handle different date formats
                for fmt in ["%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ"]:
                    try:
                        original_time = datetime.datetime.strptime(original_date, fmt)
                        app.logger.info(f"Parsed original time: {original_time}")
                        break
                    except ValueError:
                        continue
        except Exception as e:
            app.logger.warning(f"Could not parse original time: {str(e)}")
        
        # Add a random suffix to the original activity's name
        random_suffix = ''.join(random.choices('0123456789ABCDEF', k=6))
        new_name = f"{original_name} {random_suffix}"
        
        # Modify the original activity
        modify_payload = {
            "name": new_name,
            "private": True
        }
        
        modify_url = f"https://www.strava.com/api/v3/activities/{activity_id}"
        modify_response = requests.put(modify_url, headers=headers, data=json.dumps(modify_payload))
        
        if modify_response.status_code != 200:
            app.logger.error(f"Failed to modify original activity: {modify_response.status_code}")
            return jsonify({"error": "Failed to modify original activity"}), 500
            
        app.logger.info(f"Successfully modified original activity name to: {new_name}")
        
        # Wait a moment for Strava to process the changes
        time.sleep(1)
        
        # Step 5: Create new activity with the trimmed metrics but preserving original time
        
        # Use the original start time if we have it
        if original_time:
            # Format it back to string in the format Strava expects
            trimmed_metrics["start_date_local"] = original_time.strftime("%Y-%m-%dT%H:%M:%SZ")
            app.logger.info(f"Using original start time: {trimmed_metrics['start_date_local']}")
        
        # Set the name to the original name (without the suffix we added to the original)
        trimmed_metrics["name"] = original_name
        
        # Create the new activity
        app.logger.info(f"Creating new activity with name: {trimmed_metrics['name']}")
        new_activity_id = api_utils.create_activity(token, trimmed_metrics)
        
        if not new_activity_id:
            app.logger.error("Failed to create new activity")
            return jsonify({"error": "Failed to create new activity on Strava"}), 500

        app.logger.info(f"Successfully created new activity {new_activity_id}")
        
        # Step 6: Clean up the new activity by removing any suffix/prefix from name
        # and cleaning up the description
        app.logger.info(f"Cleaning up new activity {new_activity_id}")
        
        # Wait a moment to ensure the activity is fully created
        time.sleep(1)
        
        # Get the original description without the "Trimmed with Strim" text
        original_description = activity_metadata.get('description', '')
        
        # Clean up the new activity
        cleanup_success = api_utils.cleanup_activity(new_activity_id, token, original_name, original_description)
        
        if cleanup_success:
            app.logger.info(f"Successfully cleaned up activity {new_activity_id}")
        else:
            app.logger.warning(f"Failed to clean up activity {new_activity_id}, but continuing")
            # Don't fail the whole process if cleanup fails

        # Important: Return only a single success response with all necessary information
        # Include a flag to prevent additional requests
        return jsonify({
            "success": True, 
            "new_activity_id": new_activity_id,
            "original_activity_id": activity_id,
            "message": "Successfully created new activity with corrected data",
            "token": token,
            "complete": True  # Add a flag to indicate processing is complete
        })

    except Exception as e:
        app.logger.error(f"Error in /download-fit: {str(e)}")
        app.logger.error(traceback.format_exc())
        return jsonify({"error": "Internal server error", "details": str(e)}), 500

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
        activity_data = api_utils.get_activity_details(activity_id, token)
        if not activity_data:
            return jsonify({"error": "Failed to retrieve activity details from Strava"}), 500

        # Return activity data with token
        return jsonify({
            "activity": activity_data,
            "token": token  # Include token in response
        })

    except Exception as e:
        app.logger.error(f"Error in /activities/{activity_id}/details: {str(e)}")
        return jsonify({"error": "Internal server error", "details": str(e)}), 500

@app.route("/logout", methods=["POST"])
def logout():
    """Logout user by clearing session."""
    session.clear()
    return jsonify({"success": "Logged out"}), 200

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

# ---------------- END ROUTES ----------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

def create_app():
    return app