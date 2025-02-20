from flask import Flask, request, jsonify, send_file, Response
from werkzeug.utils import secure_filename
import os
import trimmer

app = Flask(__name__)
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.after_request
def add_security_headers(response):
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self'; "  
        "style-src 'self' 'unsafe-inline'; "   
        "connect-src 'self' http://localhost:5000;"  
    )
    return response

@app.route("/upload", methods=["POST"])
def upload_file():
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    filename = secure_filename(file.filename)
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(file_path)

    # Trim the activity
    trimmed_tcx = trimmer.process_file(file_path)

    return jsonify({"message": "File uploaded and trimmed successfully!", "trimmed_file": os.path.basename(trimmed_tcx)})

@app.route("/download/<filename>")
def download_file(filename):
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=True)
    else:
        return jsonify({"error": "File not found"}), 404

if __name__ == "__main__":
    app.run(debug=True, port=5000)
