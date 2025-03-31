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

# Session configuration - optimized for cross-domain use
app.config["SESSION_TYPE"] = "redis"
app.config["SESSION_PERMANENT"] = True
app.config["SESSION_LIFETIME"] = timedelta(days=7)
app.config["SESSION_USE_SIGNER"] = True
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SECURE"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "None"  # Critical for cross-domain cookies with HTTPS
app.config["SESSION_REDIS"] = redis_client
app.config["SESSION_COOKIE_PATH"] = "/"
app.config["SESSION_COOKIE_DOMAIN"] = None  # Let browser determine domain based on same-origin policy

# CORS configuration - ensure credentials support
cors = CORS()
cors.init_app(
    app,
    resources={r"/*": {
        "origins": [
            "https://strimrun.vercel.app",
            "https://strim-conner-groths-projects.vercel.app",
            # Add localhost for development
            "http://localhost:3000",
            "http://127.0.0.1:3000"
        ],
        "supports_credentials": True,  # Critical for cookies
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
        "max_age": 600
    }}
)

# Initialize Flask-Session
Session(app)

# Security Headers - with adjustments for frontend compatibility
Talisman(app, 
    content_security_policy={
        'default-src': "'self'",
        'script-src': "'self' 'unsafe-eval' https://cdnjs.cloudflare.com https://fonts.googleapis.com",
        'style-src': "'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://fonts.googleapis.com",
        'img-src': "'self' data:",
        'connect-src': "'self' https://www.strava.com",
        'font-src': "'self' https://fonts.gstatic.com",
        'report-uri': "/csp-report"  
    },
    force_https=True,
    force_https_permanent=True,
    frame_options='SAMEORIGIN',
    content_security_policy_nonce_in=['script-src'],
    strict_transport_security=True,
    strict_transport_security_preload=True,
    strict_transport_security_max_age=31536000,
    session_cookie_secure=True,
    session_cookie_http_only=True,
    feature_policy=None,
    force_file_save=False,
    content_security_policy_report_only=False,
    content_security_policy_report_uri=None,
    referrer_policy='no-referrer-when-downgrade'
)

# Create uploads directory
UPLOAD_FOLDER = "uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Helper function to get token from multiple sources
def get_token_from_request():
    """Extract the token from various sources in the request."""
    token = None
    
    # 1. Check session first
    if "strava_token" in session:
        token = session["strava_token"]
        app.logger.info("✅ Using token from session")
        
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
                    token = session["strava_token"]
                    app.logger.info("✅ Token refreshed successfully")
                else:
                    app.logger.error(f"❌ Failed to refresh token: {response.status_code} {response.text}")
            except Exception as e:
                app.logger.error(f"❌ Error refreshing token: {str(e)}")
    
    # 2. Check Authorization header as fallback
    if not token:
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
            app.logger.info("✅ Using token from Authorization header")
    
    # 3. Check query parameters as last resort
    if not token:
        token = request.args.get('token')
        if token:
            app.logger.info("✅ Using token from query parameter")
    
    # 4. For POST requests, check JSON body
    if not token and request.is_json:
        token = request.json.get('token')
        if token:
            app.logger.info("✅ Using token from request body")
    
    return token

# ---------------- ROUTES ----------------

@app.route("/")
def home():
    """Render the main page."""
    return render_template("index.html")

@app.route("/auth")
def strava_auth():
    """Redirect user to Strava OAuth login page."""
    # Store return_to URL if provided
    if request.args.get("return_to"):
        session["return_to"] = request.args.get("return_to")
    
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
    """Handle Strava OAuth callback and store the session."""
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

    # Log the client ID being used (mask part of it)
    client_id = os.getenv('STRAVA_CLIENT_ID')
    if client_id:
        masked_client_id = f"{client_id[:2]}...{client_id[-2:]}" if len(client_id) > 4 else "***"
        app.logger.info(f"📡 Using Strava client ID: {masked_client_id}")
    else:
        app.logger.error("❌ STRAVA_CLIENT_ID environment variable is missing")
        return redirect(f"{FRONTEND_URL}?auth_error=missing_client_id")
        
    # Check if client secret is set (don't log it)
    if not os.getenv('STRAVA_CLIENT_SECRET'):
        app.logger.error("❌ STRAVA_CLIENT_SECRET environment variable is missing")
        return redirect(f"{FRONTEND_URL}?auth_error=missing_client_secret")
    
    # Check if redirect URI is set
    redirect_uri = os.getenv('STRAVA_REDIRECT_URI')
    if not redirect_uri:
        app.logger.error("❌ STRAVA_REDIRECT_URI environment variable is missing")
        return redirect(f"{FRONTEND_URL}?auth_error=missing_redirect_uri")
    else:
        app.logger.info(f"📡 Using Strava redirect URI: {redirect_uri}")

    app.logger.info(f"📡 Sending token request to Strava")
    try:
        response = requests.post(token_url, data=payload, timeout=10)
        
        # Log the response status and headers (but not the body which contains sensitive info)
        app.logger.info(f"🔄 Strava token response status: {response.status_code}")
        app.logger.info(f"🔄 Strava token response headers: {dict(response.headers)}")
        
        if response.status_code != 200:
            app.logger.error(f"❌ Strava token request failed with status {response.status_code}: {response.text}")
            return redirect(f"{FRONTEND_URL}?auth_error=strava_api_error&status={response.status_code}")
            
        try:
            token_data = response.json()
        except ValueError:
            app.logger.error(f"❌ Failed to parse Strava response as JSON: {response.text[:100]}...")
            return redirect(f"{FRONTEND_URL}?auth_error=invalid_json_response")
        
        # Log token data but mask sensitive info
        safe_log_data = {k: (v if k not in ['access_token', 'refresh_token'] else '***MASKED***') 
                          for k, v in token_data.items()}
        app.logger.info(f"🔄 Strava Response: {safe_log_data}")

        if "access_token" not in token_data:
            app.logger.error(f"❌ No access token in Strava response: {safe_log_data}")
            return redirect(f"{FRONTEND_URL}?auth_error=missing_access_token")

        # Clear any existing session first
        session.clear()
        
        # Store all token data in session
        session["strava_token"] = token_data["access_token"]
        session["refresh_token"] = token_data.get("refresh_token")
        session["expires_at"] = token_data.get("expires_at")
        session["athlete"] = token_data.get("athlete")
        session.permanent = True
        
        # Force save session
        session.modified = True
        
        # Log session data (mask sensitive info)
        masked_session = {k: ('***MASKED***' if k in ['strava_token', 'refresh_token'] else v) 
                          for k, v in dict(session).items()}
        app.logger.info(f"✅ Session created: {masked_session}")
        app.logger.info(f"✅ Session ID: {request.cookies.get('session', 'unknown')}")
        
        # Include token in redirect URL for the frontend
        token = token_data["access_token"]
        encoded_token = urllib.parse.quote(token)
        redirect_url = f"{FRONTEND_URL}?auth_success=true&token={encoded_token}"
        
        # Log the redirect URL (mask the token)
        masked_redirect = redirect_url.replace(encoded_token, "***MASKED***")
        app.logger.info(f"🔀 Redirecting to: {masked_redirect}")
        
        return redirect(redirect_url)
    except requests.exceptions.RequestException as e:
        app.logger.error(f"❌ Network error during Strava token request: {str(e)}")
        return redirect(f"{FRONTEND_URL}?auth_error=network_error&message={str(e)}")
    except Exception as e:
        app.logger.error(f"❌ Unexpected error in Strava callback: {str(e)}")
        app.logger.error(traceback.format_exc())
        return redirect(f"{FRONTEND_URL}?auth_error=unexpected_error&message={str(e)}")

@app.route("/api/session-status")
def session_status():
    """Check if user is authenticated and return status."""
    app.logger.info(f"📝 Session data: {dict(session)}")
    app.logger.info(f"🍪 Request cookies: {request.cookies}")
    
    # Get token using helper function - checks all possible sources
    token = get_token_from_request()
    
    if token:
        # User is authenticated
        app.logger.info("✅ User is authenticated")
        return jsonify({
            "authenticated": True,
            "athlete": session.get("athlete"),
            "expires_at": session.get("expires_at"),
            "token": token  # Include token in response
        })
    else:
        app.logger.info("❌ User is NOT authenticated (no valid token found)")
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
    try:
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

        # Use the obtained token
        access_token = token

        # Get activity details before deletion
        activity_metadata = api_utils.get_activity_details(activity_id, access_token)
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
        trimmed_tcx = os.path.join(UPLOAD_FOLDER, f"trimmed_{activity_id}.tcx")
        trimmer.convert_to_tcx(trimmed_df, trimmed_tcx)

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

        return jsonify({
            "success": True, 
            "new_activity_id": new_activity_id,
            "token": token  # Include token in response for continuity
        })

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

    # Use the obtained token
    access_token = token

    # Fetch existing activity details
    activity_metadata = api_utils.get_activity_details(activity_id, access_token)
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

    return jsonify({
        "success": True, 
        "new_activity_id": new_activity_id,
        "token": token  # Include token in response
    })

@app.route("/logout", methods=["POST"])
def logout():
    """Logout user by clearing session."""
    session.clear()
    return jsonify({"success": "Logged out"}), 200

# Add a special route to check if the API is accessible without auth
@app.route("/api/ping", methods=["GET", "OPTIONS"])
def ping():
    """Simple endpoint to check if the API is accessible."""
    return jsonify({
        "status": "ok", 
        "message": "API is accessible",
        "session_cookie_exists": "session" in request.cookies
    }), 200

@app.after_request
def log_response_headers(response):
    """Log response headers and cookies for debugging, fix CORS headers."""
    app.logger.debug(f"Response Headers: {dict(response.headers)}")
    
    # Check if there's a session cookie in the response
    for cookie in response.headers.getlist('Set-Cookie'):
        if 'session=' in cookie:
            app.logger.debug(f"Session Cookie Found: {cookie}")
    
    # Fix CORS headers if needed - IMPORTANT: Avoid duplicating headers
    # First, check if the credentials header exists and is malformed
    if 'Access-Control-Allow-Credentials' in response.headers:
        # If it contains duplicates, fix it by explicitly setting it to 'true'
        if response.headers['Access-Control-Allow-Credentials'] != 'true':
            # Remove the existing header
            del response.headers['Access-Control-Allow-Credentials']
            # Set it correctly
            response.headers.add('Access-Control-Allow-Credentials', 'true')
    # Otherwise, for OPTIONS requests, make sure it's set
    elif request.method == 'OPTIONS':
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        
    # Ensure Access-Control-Allow-Origin is properly set (must be specific for credentials)
    origin = request.headers.get('Origin')
    if origin:
        # Check if the origin is in our allowed list
        allowed_origins = [
            "https://strimrun.vercel.app",
            "https://strim-conner-groths-projects.vercel.app",
            "http://localhost:3000",
            "http://127.0.0.1:3000"
        ]
        if origin in allowed_origins:
            # Remove any existing header
            if 'Access-Control-Allow-Origin' in response.headers:
                del response.headers['Access-Control-Allow-Origin']
            # Set the specific origin (not '*' which would break credentials)  
            response.headers.add('Access-Control-Allow-Origin', origin)
        
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