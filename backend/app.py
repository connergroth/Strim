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

# Update the Flask session configuration in app.py
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY")
if not app.config["SECRET_KEY"]:
    logger.error("SECRET_KEY not found in environment variables.")
    sys.exit(1)  # Exit if secret key is not set in production
    
app.config["SESSION_TYPE"] = "redis"
app.config["SESSION_PERMANENT"] = True
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)
app.config["SESSION_USE_SIGNER"] = True
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SECURE"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "None"  # Critical for cross-domain cookies
app.config["SESSION_REDIS"] = redis_client

# And ensure your CORS configuration includes 'credentials' support
CORS(app, 
    supports_credentials=True,  
    origins=[
        "https://strimrun.vercel.app",
        "https://strim-conner-groths-projects.vercel.app",
    ],
    allow_headers=[
        "Content-Type", 
        "Authorization", 
        "X-Requested-With", 
        "Accept", 
        "Origin", 
        "Cache-Control"  
    ],
    methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    expose_headers=["Content-Type", "X-CSRFToken", "Set-Cookie"],  # Expose Set-Cookie header
    max_age=600
)

# Security Headers
Talisman(app, content_security_policy={
    'default-src': "'self'",
    'script-src': "'self' 'unsafe-eval' https://cdnjs.cloudflare.com https://fonts.googleapis.com",
    'style-src': "'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://fonts.googleapis.com",
    'img-src': "'self' data:",
    'report-uri': "/csp-report"  
})

UPLOAD_FOLDER = "uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ---------------- ROUTES ----------------

@app.route("/")
def home():
    """Render the main page."""
    return render_template("index.html")

@app.route("/auth")
def strava_auth():
    """Redirect user to Strava OAuth login page."""
    if request.args.get("return_to"):
        session["return_to"] = request.args.get("return_to")
        
    auth_url = (
        f"https://www.strava.com/oauth/authorize"
        f"?client_id={os.getenv('STRAVA_CLIENT_ID')}"
        f"&response_type=code"
        f"&redirect_uri={os.getenv('STRAVA_REDIRECT_URI')}"
        f"&scope=activity:read,activity:read_all,activity:write"
    )
    return redirect(auth_url)

@app.route("/auth/callback", methods=["GET"])
def strava_callback():
    """Handle Strava OAuth callback and store the session."""
    code = request.args.get("code")
    
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

    app.logger.info(f"📡 Sending request to Strava: {payload}")
    try:
        response = requests.post(token_url, data=payload)
        token_data = response.json()
        
        # Log token data but mask sensitive info
        safe_log_data = {k: (v if k not in ['access_token', 'refresh_token'] else '***MASKED***') 
                          for k, v in token_data.items()}
        app.logger.info(f"🔄 Strava Response: {safe_log_data}")

        if "access_token" in token_data:
            # Store all token data in session
            session["strava_token"] = token_data["access_token"]
            session["refresh_token"] = token_data.get("refresh_token")
            session["expires_at"] = token_data.get("expires_at")
            session["athlete"] = token_data.get("athlete")
            session.permanent = True
            
            # Force save session
            session.modified = True
            
            app.logger.info(f"✅ Session created and stored. Session ID: {request.cookies.get('session', 'unknown')}")
            
            # Redirect to frontend
            resp = redirect(f"{FRONTEND_URL}?auth_success=true")
            app.logger.info(f"🔀 Redirecting to: {FRONTEND_URL}?auth_success=true")
            return resp
        else:
            app.logger.error(f"Failed to get access token: {token_data}")
            return redirect(f"{FRONTEND_URL}?auth_error=strava_token_failure")
    except Exception as e:
        app.logger.error(f"Error in Strava callback: {str(e)}")
        return redirect(f"{FRONTEND_URL}?auth_error=exception&message={str(e)}")

@app.route("/api/session-status")
def session_status():
    """Check if user is authenticated and return status."""
    app.logger.info(f"📝 Session data: {dict(session)}")
    app.logger.info(f"🍪 Request cookies: {request.cookies}")
    
    if "strava_token" in session:
        # Check if token is expired and refresh if needed
        if session.get("expires_at") and time.time() > session.get("expires_at"):
            try:
                app.logger.info("🔄 Token expired, attempting to refresh...")
                # Refresh token logic
                token_url = "https://www.strava.com/oauth/token"
                payload = {
                    "client_id": os.getenv('STRAVA_CLIENT_ID'),
                    "client_secret": os.getenv('STRAVA_CLIENT_SECRET'),
                    "refresh_token": session.get("refresh_token"),
                    "grant_type": "refresh_token"
                }
                response = requests.post(token_url, data=payload)
                if response.status_code == 200:
                    token_data = response.json()
                    session["strava_token"] = token_data["access_token"]
                    session["refresh_token"] = token_data.get("refresh_token")
                    session["expires_at"] = token_data.get("expires_at")
                    session.modified = True
                    app.logger.info("✅ Token refreshed successfully")
                else:
                    app.logger.error(f"❌ Failed to refresh token: {response.status_code} {response.text}")
                    session.clear()
                    return jsonify({"authenticated": False, "reason": "token_refresh_failed"})
            except Exception as e:
                app.logger.error(f"❌ Error refreshing token: {str(e)}")
                session.clear()
                return jsonify({"authenticated": False, "reason": "token_refresh_error"})
                
        # User is authenticated
        app.logger.info("✅ User is authenticated")
        return jsonify({
            "authenticated": True,
            "athlete": session.get("athlete"),
            "expires_at": session.get("expires_at")
        })
    else:
        app.logger.info("❌ User is NOT authenticated (no token in session)")
        return jsonify({"authenticated": False, "reason": "no_token"})

@app.route("/activities", methods=["GET"])
def get_activities():
    """Retrieve user activities from Strava API."""
    app.logger.info(f"📝 Request to /activities - Session data: {dict(session)}")
    app.logger.info(f"🍪 Request cookies: {request.cookies}")
    
    if "strava_token" not in session:
        # Check if token is in Authorization header (fallback mechanism)
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
            app.logger.info("Using token from Authorization header")
        else:
            app.logger.info("❌ No token in session or header")
            return jsonify({"error": "Unauthorized. No valid session token."}), 401
    else:
        # Get token from session
        token = session["strava_token"]
        app.logger.info("✅ Using token from session")

    # Get activities from Strava
    url = "https://www.strava.com/api/v3/athlete/activities"
    headers = {"Authorization": f"Bearer {token}"}

    app.logger.info(f"📡 Sending request to Strava API")
    response = requests.get(url, headers=headers)
    
    if response.status_code != 200:
        app.logger.error(f"❌ Strava API error: {response.status_code}")
        return jsonify({"error": "Failed to fetch activities from Strava"}), response.status_code

    activities = response.json()
    app.logger.info(f"✅ Received {len(activities)} activities from Strava")
    
    # Include the token in the response as a fallback mechanism
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
    try:
        if "strava_token" not in session:
            return jsonify({"error": "Unauthorized"}), 401

        activity_id = request.args.get("activity_id")
        edit_distance = request.args.get("edit_distance") == "true"
        new_distance = request.args.get("new_distance")

        if not activity_id:
            return jsonify({"error": "Missing activity ID"}), 400

        if edit_distance and (not new_distance or float(new_distance) <= 0):
            return jsonify({"error": "Invalid new distance provided"}), 400

        # Get Access Token
        access_token = api_utils.get_access_token()

        # Get activity details before deletion
        activity_metadata = api_utils.get_activity_details(activity_id)
        if not activity_metadata:
            return jsonify({"error": "Failed to retrieve activity details"}), 500

        # Download original FIT file from Strava
        fit_url = f"https://www.strava.com/api/v3/activities/{activity_id}/export_original"
        headers = {"Authorization": f"Bearer {access_token}"}

        response = requests.get(fit_url, headers=headers, stream=True)
        if response.status_code != 200:
            return jsonify({"error": "Failed to download FIT file"}), 500

        fit_path = os.path.join(UPLOAD_FOLDER, f"{activity_id}.fit")
        with open(fit_path, "wb") as fit_file:
            for chunk in response.iter_content(chunk_size=1024):
                fit_file.write(chunk)

        # Process FIT file (trim stops and optionally edit distance)
        df = trimmer.load_fit(fit_path)
        end_timestamp = trimmer.detect_stop(df)
        trimmed_df = trimmer.trim(df, end_timestamp, float(new_distance) if edit_distance else None)

        # Convert to TCX format
        trimmed_tcx = trimmer.convert_to_tcx(trimmed_df, f"{UPLOAD_FOLDER}/trimmed_{activity_id}.tcx")

        # Step 1: Delete old activity from Strava
        delete_success = api_utils.delete_activity(activity_id, access_token)
        if not delete_success:
            return jsonify({"error": "Failed to delete original activity"}), 500

        # Step 2: Upload new trimmed activity
        upload_id = api_utils.upload_tcx(access_token, trimmed_tcx, activity_metadata["name"])
        if not upload_id:
            return jsonify({"error": "Failed to upload new activity"}), 500

        # Step 3: Wait for Strava to process the uploaded activity
        new_activity_id = api_utils.check_upload_status(access_token, upload_id)
        if not new_activity_id:
            return jsonify({"error": "Upload processing failed"}), 500

        return jsonify({"success": True, "new_activity_id": new_activity_id})

    except Exception as e:
        app.logger.error(f"Error in /download-fit: {str(e)}\n{traceback.format_exc()}")
        return jsonify({"error": "Internal server error", "details": str(e)}), 500

@app.route("/activity-selection")
def activity_selection():
    """Render the activity selection page."""
    return render_template("index.html")

@app.route("/update-distance", methods=["POST"])
def update_distance():
    """Update activity distance and re-upload to Strava."""
    if "strava_token" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json
    activity_id = data.get("activity_id")
    new_distance = data.get("new_distance")

    if not activity_id or not new_distance:
        return jsonify({"error": "Missing required data"}), 400

    access_token = api_utils.get_access_token()

    # Fetch existing activity details
    activity_metadata = api_utils.get_activity_details(activity_id)
    if not activity_metadata:
        return jsonify({"error": "Failed to fetch activity details"}), 500

    # Update metadata with new distance
    activity_metadata["distance"] = float(new_distance)

    # Delete original activity
    delete_success = api_utils.delete_activity(activity_id, access_token)
    if not delete_success:
        return jsonify({"error": "Failed to delete original activity"}), 500

    # Recreate activity with updated distance
    new_activity_id = api_utils.create_activity(access_token, activity_metadata)
    if not new_activity_id:
        return jsonify({"error": "Failed to create new activity"}), 500

    return jsonify({"success": True, "new_activity_id": new_activity_id})

@app.route("/logout", methods=["POST"])
def logout():
    """Logout user by clearing session."""
    session.clear()
    return jsonify({"success": "Logged out"}), 200

# Add a special route to check if the API is accessible without auth
@app.route("/api/ping", methods=["GET", "OPTIONS"])
def ping():
    """Simple endpoint to check if the API is accessible."""
    return jsonify({"status": "ok", "message": "API is accessible"}), 200

@app.after_request
def log_response_headers(response):
    """Log response headers and cookies for debugging."""
    app.logger.debug(f"Response Headers: {dict(response.headers)}")
    
    # Check if there's a session cookie in the response
    for cookie in response.headers.getlist('Set-Cookie'):
        if 'session=' in cookie:
            app.logger.debug(f"Session Cookie Found: {cookie}")

    return response

@app.context_processor
def inject_env_variables():
    return {
        "BASE_URL": BASE_URL,
        "FRONTEND_URL": FRONTEND_URL,
        "ENVIRONMENT": "production"
    }

# ---------------- END ROUTES ----------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

def create_app():
    return app