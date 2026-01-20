import os
import uuid
from flask import Flask, request, jsonify, send_file
import yt_dlp

app = Flask(__name__)

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# =========================
# 共通 yt-dlp オプション
# =========================
COMMON_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "js_runtimes": ["node"],  # ★超重要（SABR / JS対策）
    "http_headers": {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    },
    "source_address": "0.0.0.0",  # IPv6問題回避
}

# =========================
# 動画情報取得
# =========================
@app.route("/get_info", methods=["POST"])
def get_info():
    url = request.json.get("url")
    if not url:
        return jsonify({"error": "URL is required"}), 400

    try:
        with yt_dlp.YoutubeDL(COMMON_OPTS) as ydl:
            info = ydl.extract_info(url, download=False)

        return jsonify({
            "title": info.get("title"),
            "duration": info.get("duration"),
            "thumbnail": info.get("thumbnail")
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =========================
# ダウンロード（mp4 / mp3）
# =========================
@app.route("/enqueue", methods=["POST"])
def enqueue():
    url = request.json.get("url")
    mode = request.json.get("mode", "mp4")  # mp4 or mp3

    if not url:
        return jsonify({"error": "URL is required"}), 400

    file_id = str(uuid.uuid4())

    try:
        if mode == "mp3":
            filename = f"{file_id}.mp3"
            filepath = os.path.join(DOWNLOAD_DIR, filename)

            ydl_opts = {
                **COMMON_OPTS,
                "format": "bestaudio",
                "outtmpl": filepath,
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }],
            }

        else:  # mp4
            filename = f"{file_id}.mp4"
            filepath = os.path.join(DOWNLOAD_DIR, filename)

            ydl_opts = {
                **COMMON_OPTS,
                "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best",
                "merge_output_format": "mp4",
                "outtmpl": filepath,
            }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        # ===== 空ファイル対策 =====
        if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
            raise Exception("Downloaded file is empty")

        return jsonify({
            "status": "completed",
            "download_url": f"/download/{filename}"
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =========================
# ファイル配信
# =========================
@app.route("/download/<filename>")
def download_file(filename):
    filepath = os.path.join(DOWNLOAD_DIR, filename)

    if not os.path.exists(filepath):
        return jsonify({"error": "File not found"}), 404

    return send_file(filepath, as_attachment=True)


# =========================
# Railway / Render 対応
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
