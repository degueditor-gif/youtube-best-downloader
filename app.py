from flask import Flask, request, jsonify, send_from_directory, render_template
import yt_dlp
import os
import threading
import re

app = Flask(__name__)

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def sanitize_filename(name):
    return re.sub(r'[\\/:*?"<>|]', '_', name)


def download_task(url, format_type):
    try:
        if format_type == "mp3":
            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": f"{DOWNLOAD_DIR}/%(title)s.%(ext)s",
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "192",
                    }
                ],
                "restrictfilenames": False,
                "quiet": True,
                "no_warnings": True,
            }

        else:  # mp4
            ydl_opts = {
                "format": "bestvideo+bestaudio/best",
                "outtmpl": f"{DOWNLOAD_DIR}/%(title)s.%(ext)s",
                "merge_output_format": "mp4",
                "quiet": True,
                "no_warnings": True,
            }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

            # ファイル名を安全なものに変更
            title = sanitize_filename(info.get("title", "video"))

            if format_type == "mp3":
                filename = f"{title}.mp3"
            else:
                filename = f"{title}.mp4"

            original_path = os.path.join(DOWNLOAD_DIR, filename)
            if os.path.exists(original_path):
                return filename

    except Exception as e:
        print("❌ Download error:", e)

    return None


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

    result = {"filename": None}

    def task():
        result["filename"] = download_task(url, format_type)

    thread = threading.Thread(target=task, daemon=True)
    thread.start()
    thread.join()  # WEB用途なので完了まで待つ

    if not result["filename"]:
        return jsonify({"error": "download failed"}), 500

    return jsonify({"filename": result["filename"]})


@app.route("/file/<path:filename>")
def get_file(filename):
    return send_from_directory(
        DOWNLOAD_DIR,
        filename,
        as_attachment=True
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
