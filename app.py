from flask import Flask, request, jsonify, send_from_directory, render_template
import yt_dlp
import os
import threading
import uuid

app = Flask(__name__)

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def download_task(url, format_type, task_id):
    try:
        if format_type == "mp3":
            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": f"{DOWNLOAD_DIR}/{task_id}.%(ext)s",
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "192",
                    }
                ],
                "quiet": True,
                "no_warnings": True,
            }
        else:  # mp4
            ydl_opts = {
                "format": "bestvideo+bestaudio/best",
                "outtmpl": f"{DOWNLOAD_DIR}/{task_id}.%(ext)s",
                "merge_output_format": "mp4",
                "quiet": True,
                "no_warnings": True,
            }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

    except Exception as e:
        print("❌ Download error:", e)


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

    thread = threading.Thread(
        target=download_task,
        args=(url, format_type, task_id),
        daemon=True
    )
    thread.start()

    return jsonify({"task_id": task_id})


@app.route("/file/<task_id>")
def get_file(task_id):
    for file in os.listdir(DOWNLOAD_DIR):
        if file.startswith(task_id):
            return send_from_directory(
                DOWNLOAD_DIR,
                file,
                as_attachment=True
            )

    return jsonify({"error": "file not ready"}), 404


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
