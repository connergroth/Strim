from flask import Flask, request, redirect, jsonify, session, render_template, url_for
from flask_session import Session
from flask_cors import CORS
from flask_talisman import Talisman
from datetime import timedelta
import requests
import traceback
import redis
import time
import os

import api_utils
import trimmer

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Define base directories
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

app = Flask(
    __name__, 
    template_folder=os.path.join(FRONTEND_DIR, "templates"),  
    static_folder=os.path.join(FRONTEND_DIR, "static"),
    static_url_path="/static" 
)

# CORS Configuration
CORS(app, 
    supports_credentials=True,  
    origins=[
        "https://strimrun.vercel.app",
        "https://strim-conner-groths-projects.vercel.app",  
        "http://localhost:3000",  
        "http://127.0.0.1:8080",
        "http://localhost:8080"
    ],
    allow_headers=["Content-Type", "Authorization"],
    methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"]
) 

# Security Headers
Talisman(app, content_security_policy={
    'default-src': "'self'",
    'script-src': "'self' 'unsafe-eval' https://cdnjs.cloudflare.com https://fonts.googleapis.com",
    'style-src': "'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://fonts.googleapis.com",
    'img-src': "'self' data:",
    'report-uri': "/csp-report"  
})

# Environment configuration
BASE_URL = "https://strim-production.up.railway.app"
FRONTEND_URL = "https://strimrun.vercel.app"
REDIS_URL = os.getenv("REDIS_URL")

# Flask session configuration
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "supersecretkey")
app.config["SESSION_TYPE"] = "redis"  
app.config["SESSION_PERMANENT"] = True
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)
app.config["SESSION_USE_SIGNER"] = True  
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SECURE"] = True if os.getenv("ENVIRONMENT") == "production" else False
app.config["SESSION_COOKIE_SAMESITE"] = "None" if os.getenv("ENVIRONMENT") == "production" else "Lax"
app.config["SESSION_REDIS"] = redis.from_url(REDIS_URL)

Session(app)

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
        return redirect(url_for("home", error="Missing authorization code"))

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
        app.logger.info(f"🔄 Strava Response: {token_data}")

        if "access_token" in token_data:
            # Store all token data in session
            session["strava_token"] = token_data["access_token"]
            session["refresh_token"] = token_data.get("refresh_token")
            session["expires_at"] = token_data.get("expires_at")
            session["athlete"] = token_data.get("athlete")
            session.permanent = True
            session.modified = True

            app.logger.info(f"✅ After storing token, session: {dict(session)}")
            
            return redirect(FRONTEND_URL)
        else:
            return redirect(url_for("home", error="Failed to authenticate with Strava"))
    except Exception as e:
        app.logger.error(f"Error in Strava callback: {str(e)}")
        return redirect(url_for("home", error="Authentication error"))

@app.route("/api/session-status")
def session_status():
    """Check if user is authenticated and return status."""
    if "strava_token" in session:
        if session.get("expires_at") and time.time() > session.get("expires_at"):
            try:
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
                else:
                    # Failed to refresh, consider user logged out
                    session.clear()
                    return jsonify({"authenticated": False})
            except Exception as e:
                app.logger.error(f"Error refreshing token: {str(e)}")
                session.clear()
                return jsonify({"authenticated": False})
                
        # User is authenticated
        return jsonify({
            "authenticated": True,
            "athlete": session.get("athlete")
        })
    else:
        return jsonify({"authenticated": False})

@app.route("/activities", methods=["GET"])
def get_activities():
    """Retrieve user activities from Strava API."""
    if "strava_token" not in session:
        return jsonify({"error": "Unauthorized. No valid session token."}), 401

    access_token = session["strava_token"]
    url = "https://www.strava.com/api/v3/athlete/activities"
    headers = {"Authorization": f"Bearer {access_token}"}

    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        return jsonify({"error": "Failed to fetch activities"}), 500

    activities = response.json()
    return jsonify({"activities": [
        {
            "id": act["id"],
            "name": act["name"],
            "distance_miles": round(act["distance"] / 1609.34, 2),
            "date": act["start_date_local"]
        }
        for act in activities if act["type"] == "Run"
    ]})

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

@app.after_request
def log_response_headers(response):
    """Log response headers for debugging."""
    return response

@app.context_processor
def inject_env_variables():
    return {
        "BASE_URL": BASE_URL,
        "FRONTEND_URL": FRONTEND_URL,
        "ENVIRONMENT": os.getenv("ENVIRONMENT", "development")
    }

# ---------------- END ROUTES ----------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(debug=True, host="0.0.0.0", port=port)

def create_app():
    return app