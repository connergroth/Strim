from flask import Flask, Response, request, redirect, jsonify, send_file, send_from_directory, session, render_template
from flask_session import Session
from flask_cors import CORS
from werkzeug.utils import secure_filename
from flask_talisman import Talisman
import requests
import trimmer
import logging

import os
from dotenv import load_dotenv
load_dotenv()

# Start Session
app = Flask(__name__)

CORS(app, supports_credentials=True, origins=["http://localhost:5500"])  

Talisman(app, content_security_policy={
    'default-src': "'self'",
    'script-src': "'self' 'unsafe-eval' https://cdnjs.cloudflare.com https://fonts.googleapis.com",
    'style-src': "'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://fonts.googleapis.com",
}, content_security_policy_report_only=True, content_security_policy_report_uri="/csp-report")

# Ensure Session is Stored on Disk
SESSION_DIR = os.path.abspath("./flask_session")  
if not os.path.exists(SESSION_DIR):
    os.makedirs(SESSION_DIR)  # Create the session directory if it doesn’t exist

app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "supersecretkey")
app.config["SESSION_TYPE"] = "filesystem"  # Store sessions on disk
app.config["SESSION_FILE_DIR"] = SESSION_DIR  # Save session files here
app.config["SESSION_PERMANENT"] = True  # Ensure session persists
app.config["SESSION_USE_SIGNER"] = True  # Prevents tampering
app.config["SESSION_COOKIE_HTTPONLY"] = True  # Prevents JS access to session
app.config["SESSION_COOKIE_SECURE"] = False  # Set to True in production
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"  # Ensures session persists across redirects

Session(app)

# Logging 
logging.basicConfig(filename="strim.log", level=logging.INFO, 
                    format="%(asctime)s - %(levelname)s - %(message)s")

app.logger.info("Strim app started")

@app.route("/")
def home():
    return "You are logged in! Now select an activity to trim."

@app.route("/auth")
def strava_auth():
    auth_url = (
        f"https://www.strava.com/oauth/authorize"
        f"?client_id={os.getenv('STRAVA_CLIENT_ID')}"
        f"&response_type=code"
        f"&redirect_uri={os.getenv('STRAVA_REDIRECT_URI')}"
        f"&scope=activity:read,activity:write"
    )
    return redirect(auth_url)

@app.route("/auth/status", methods=["GET"])
def auth_status():
    app.logger.info(f"Session contents: {session}")  # Debug session issue
    return jsonify({"authenticated": "strava_token" in session})

@app.route("/auth/callback")
def strava_callback():
    code = request.args.get("code")

    if not code:
        app.logger.warning("No authorization code received")
        return jsonify({"error": "No authorization code received"}), 400

    try:
        response = requests.post("https://www.strava.com/oauth/token", data={
            "client_id": os.getenv("STRAVA_CLIENT_ID"),
            "client_secret": os.getenv("STRAVA_CLIENT_SECRET"),
            "code": code,
            "grant_type": "authorization_code"
        })

        if response.status_code != 200:
            app.logger.error(f"Strava API Error: {response.json()}")
            return jsonify({"error": "Failed to exchange code for token", "details": response.json()}), 500

        token_data = response.json()

        # Store tokens in session
        session["strava_token"] = token_data.get("access_token")
        session["refresh_token"] = token_data.get("refresh_token")
        session["expires_at"] = token_data.get("expires_at")

        app.logger.info(f"Session after login: {session}")  # Debugging session

        return redirect("/activity-selection")

    except requests.exceptions.RequestException as e:
        app.logger.error(f"Request Error: {str(e)}")
        return jsonify({"error": "Request to Strava failed", "details": str(e)}), 500

@app.route("/get-activities", methods=["GET"])
def get_activities():
    if "strava_token" not in session:
        app.logger.warning("Unauthorized request to get activities. Session contents:")
        app.logger.warning(session)  # Debugging session issue
        return jsonify({"error": "Unauthorized. No valid session token."}), 401

    access_token = session["strava_token"]
    url = "https://www.strava.com/api/v3/athlete/activities"
    headers = {"Authorization": f"Bearer {access_token}"}

    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        app.logger.error(f"Failed to fetch activities: {response.json()}")
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

@app.route("/activity-selection")
def activity_selection():
    return render_template("index.html")  

@app.route("/update-distance", methods=["POST"])
def update_distance():
    if "strava_token" not in session:
        return jsonify({"error": "Unauthorized"})

    data = request.json
    activity_id = data.get("activity_id")
    corrected

@app.route("/download-fit", methods=["GET"])
def download_fit():
    if "strava_token" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    activity_id = request.args.get("activity_id")
    if not activity_id:
        return jsonify({"error": "Missing activity ID"}), 400

    access_token = session["strava_token"]
    fit_url = f"https://www.strava.com/api/v3/activities/{activity_id}/export_original"

    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(fit_url, headers=headers)

    if response.status_code != 200:
        return jsonify({"error": "Failed to download FIT file"}), 500

    # Save the file
    fit_path = f"uploads/{activity_id}.fit"
    with open(fit_path, "wb") as fit_file:
        fit_file.write(response.content)

    # Step 1: Trim the activity
    df = trimmer.load_fit(fit_path)
    end_timestamp = trimmer.detect_stop(df)
    trimmed_df = trimmer.trim(df, end_timestamp)

    # Step 2: Convert and Modify Distance
    corrected_distance = trimmed_df["distance"].max()
    corrected_tcx = trimmer.convert_to_tcx(trimmed_df, f"uploads/trimmed_{activity_id}.tcx", corrected_distance)

    # Step 3: Delete old activity and re-upload the trimmed one
    utils.delete_activity(activity_id, access_token)
    upload_id = utils.upload_tcx(access_token, corrected_tcx)

    if upload_id:
        new_activity_id = utils.check_upload_status(access_token, upload_id)
        return jsonify({"success": True, "new_activity_id": new_activity_id})
    else:
        return jsonify({"error": "Failed to upload trimmed activity"}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)