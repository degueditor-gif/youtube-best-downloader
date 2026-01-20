from flask import Flask, request, jsonify, send_from_directory, render_template
import yt_dlp
import os
import threading
import re
import uuid
import time

app = Flask(__name__)

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

tasks = {}


def sanitize_filename(name):
    return re.sub(r'[\\/:*?"<>|]', '_', name)


def download_task(url, format_type, task_id):
    try:
        if format_type == "mp3":
            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": f"{DOWNLOAD_DIR}/%(title)s.%(ext)s",
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }],
                "quiet": True,
                "no_warnings": True,
            }
        else:
            ydl_opts = {
                "format": "bestvideo+bestaudio/best",
                "outtmpl": f"{DOWNLOAD_DIR}/%(title)s.%(ext)s",
                "merge_output_format": "mp4",
                "quiet": True,
                "no_warnings": True,
            }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = sanitize_filename(info.get("title", "video"))

        filename = f"{title}.mp3" if format_type == "mp3" else f"{title}.mp4"
        tasks[task_id] = filename

    except Exception as e:
        print("❌ Download error:", e)
        tasks[task_id] = "ERROR"


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/download", methods=["POST"])
def download():
    data = request.json
    url = data.get("url")
    format_type = data.get("format")

    if not url or format_type not in ["mp3", "mp4"]:
        return jsonify({"error": "invalid request"}), 400

    task_id = str(uuid.uuid4())
    tasks[task_id] = "PROCESSING"

    threading.Thread(
        target=download_task,
        args=(url, format_type, task_id),
        daemon=True
    ).start()

    return jsonify({"task_id": task_id})


@app.route("/status/<task_id>")
def status(task_id):
    return jsonify({"status": tasks.get(task_id, "UNKNOWN")})


@app.route("/file/<path:filename>")
def get_file(filename):
    return send_from_directory(DOWNLOAD_DIR, filename, as_attachment=True)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
