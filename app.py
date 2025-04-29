from flask import Flask, request, jsonify
from scraper import scrape_website, save_content_to_txt
from urllib.parse import urlparse
import requests
import os
import uuid
from waitress import serve
from pathlib import Path

app = Flask(__name__)
UPLOAD_API = "https://careai-657352464140.us-central1.run.app/upload"
MAX_FILE_SIZE = 900_000  # bytes (to be safe under Firestore 1MB limit)


def split_file_by_size(original_file_path, output_dir, max_bytes=MAX_FILE_SIZE):
    part_files = []
    part_number = 1
    current_lines = []
    current_size = 0

    with open(original_file_path, "r", encoding="utf-8") as f:
        for line in f:
            encoded_line = line.encode("utf-8")
            if current_size + len(encoded_line) > max_bytes:
                part_path = os.path.join(output_dir, f"data{part_number}.txt")
                with open(part_path, "w", encoding="utf-8") as part_file:
                    part_file.writelines(current_lines)
                part_files.append(part_path)
                part_number += 1
                current_lines = []
                current_size = 0
            current_lines.append(line)
            current_size += len(encoded_line)

        # Save the last part
        if current_lines:
            part_path = os.path.join(output_dir, f"data{part_number}.txt")
            with open(part_path, "w", encoding="utf-8") as part_file:
                part_file.writelines(current_lines)
            part_files.append(part_path)

    return part_files


@app.route("/scrape", methods=["POST"])
def scrape():
    try:
        data = request.get_json()
        url = data.get("url")
        org_id = data.get("orgId")
        max_depth = data.get("depth", 1)

        if not url or not org_id:
            return jsonify({"error": "Both 'url' and 'orgId' are required"}), 400

        parsed_url = urlparse(url)
        if not all([parsed_url.scheme, parsed_url.netloc]):
            return jsonify({"error": "Invalid URL format"}), 400

        lines = scrape_website(url, depth=0, max_depth=max_depth)

        if not lines:
            return jsonify({
                "message": "No content scraped",
                "warning": "Check URL or scraping restrictions"
            }), 204

        # Unique folder for each request (multi-user support)
        request_id = str(uuid.uuid4())
        output_folder = f"temp_uploads/{request_id}"
        Path(output_folder).mkdir(parents=True, exist_ok=True)

        original_file = os.path.join(output_folder, "scraped_content.txt")
        save_content_to_txt(lines, filename=original_file)

        part_files = split_file_by_size(original_file, output_folder)
        upload_responses = []

        for file_path in part_files:
            file_size = os.path.getsize(file_path)
            if file_size > MAX_FILE_SIZE:
                upload_responses.append({
                    "file": os.path.basename(file_path),
                    "status": 400,
                    "error": f"File too large after split: {file_size} bytes"
                })
                continue

            with open(file_path, "rb") as f:
                res = requests.post(
                    f"{UPLOAD_API}?orgId={org_id}",
                    files={"file": f}
                )
                upload_responses.append({
                    "file": os.path.basename(file_path),
                    "status": res.status_code,
                    "response": res.json() if res.headers.get("content-type", "").startswith("application/json") else res.text
                })

            os.remove(file_path)

        os.remove(original_file)
        os.rmdir(output_folder)

        return jsonify({
            "message": "Scraping and upload complete",
            "parts_uploaded": len(part_files),
            "upload_responses": upload_responses,
            "sample": lines[:10],
            "total_lines": len(lines)
        })

    except Exception as e:
        return jsonify({"error": "Scraping or upload failed", "details": str(e)}), 500


if __name__ == "__main__":
    Path("temp_uploads").mkdir(exist_ok=True)
    serve(app, host="0.0.0.0", port=8080)
