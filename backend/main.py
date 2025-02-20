import os
import time
import requests
from upload import get_access_token, delete_activity, get_activity_details, upload_tcx, check_upload_status
from trimmer import load_fit, detect_stop, trim, convert_to_tcx

# Load environment variables
ACCESS_TOKEN = get_access_token()

# Fetch and save original activity metadata
ACTIVITY_ID = "your_activity_id_here"  # Replace with actual ID
activity_metadata = get_activity_details(ACTIVITY_ID)

# Delete the original activity
if activity_metadata:
    delete_activity(ACTIVITY_ID, ACCESS_TOKEN)

# Load, detect stop, and trim the run
file = "Night_Run.fit"
df = load_fit(file)
end = detect_stop(df)
trimmed_run = trim(end, df)

# Convert to TCX
trimmed_tcx_path = "trimmed_run.tcx"
convert_to_tcx(trimmed_run, trimmed_tcx_path)

# Upload trimmed TCX file to Strava
upload_id = upload_tcx(ACCESS_TOKEN, trimmed_tcx_path)

# Check upload status and get new activity ID
if upload_id:
    new_activity_id = check_upload_status(ACCESS_TOKEN, upload_id)
    print(f"New trimmed activity ID: {new_activity_id}")
