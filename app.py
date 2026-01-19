from flask import Flask, render_template, request, send_file, jsonify
from flask_socketio import SocketIO
import yt_dlp
import os
import re
import threading
import queue
import time

app = Flask(__name__)
# どのスレッドからでも通信できるように、async_modeを明示
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

DOWNLOAD_FOLDER = 'downloads'
if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

download_queue = queue.Queue()
cancel_list = set()

def sanitize_filename(filename):
    return re.sub(r'[\\/*?:"<>|]', "", filename)

def progress_hook(d):
    """ダウンロードの進捗を解析して全ユーザーに送信"""
    if d['status'] == 'downloading':
        # 進捗文字列（" 45.2%"など）から数値だけを抽出
        p = d.get('_percent_str', '0%')
        p_clean = re.sub(r'[^0-9.]', '', p)
        try:
            percent = float(p_clean)
            # namespace='/' を指定することで確実にフロントエンドへ届ける
            socketio.emit('progress_update', {
                'percent': round(percent * 0.9, 1), 
                'status': 'ダウンロード中...'
            }, namespace='/')
        except:
            pass
    elif d['status'] == 'finished':
        socketio.emit('progress_update', {
            'percent': 95, 
            'status': 'ダウンロード中...'
        }, namespace='/')

def process_queue():
    """バックグラウンドでキューを監視して1つずつ処理"""
    while True:
        task = download_queue.get()
        if task is None: break
        
        url, mode, format_id, title, task_id = task
        if task_id in cancel_list:
            download_queue.task_done()
            continue

        try:
            socketio.emit('task_status', {'task_id': task_id, 'status': '開始'}, namespace='/')
            output_base = os.path.join(DOWNLOAD_FOLDER, task_id)
            
            common_opts = {
                'progress_hooks': [progress_hook],
                'quiet': True,
                'no_warnings': True,
                'writethumbnail': True,
            }

            if mode == 'mp3':
                ydl_opts = {
                    **common_opts,
                    'format': 'bestaudio/best',
                    'outtmpl': output_base,
                    'postprocessors': [
                        {'key': 'FFmpegExtractAudio','preferredcodec': 'mp3','preferredquality': '192'},
                        {'key': 'EmbedThumbnail'},
                        {'key': 'FFmpegMetadata'},
                    ],
                }
                ext = "mp3"
            else:
                ydl_opts = {
                    **common_opts,
                    'format': f'{format_id}+bestaudio/best',
                    'outtmpl': f"{output_base}.mp4",
                    'merge_output_format': 'mp4',
                }
                ext = "mp4"

            full_path = f"{output_base}.{ext}"
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            
            if task_id not in cancel_list:
                socketio.emit('task_complete', {
                    'task_id': task_id, 
                    'download_url': f'/get_file/{task_id}/{ext}/{sanitize_filename(title)}'
                }, namespace='/')
            
        except Exception as e:
            socketio.emit('task_error', {'task_id': task_id, 'error': str(e)}, namespace='/')
        
        download_queue.task_done()

# サーバー起動と同時にバックグラウンド処理を開始
threading.Thread(target=process_queue, daemon=True).start()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get_info', methods=['POST'])
def get_info():
    url = request.json.get('url')
    ydl_opts = {'extract_flat': 'in_playlist', 'quiet': True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if 'entries' in info:
                videos = [{'id': e['id'], 'title': e['title'], 'url': f"https://www.youtube.com/watch?v={e['id']}", 'thumbnail': e['thumbnails'][0]['url'] if e.get('thumbnails') else ""} for e in info['entries'] if e]
                return jsonify({'type': 'playlist', 'title': info['title'], 'videos': videos})
            else:
                formats = []
                for f in info['formats']:
                    if f.get('height') and isinstance(f.get('height'), int):
                        size = f.get('filesize') or f.get('filesize_approx') or 0
                        formats.append({
                            'id': f['format_id'], 'res': f'{f["height"]}p', 'height': f['height'],
                            'size': f"{round(size / 1024 / 1024, 1)}MB" if size > 0 else "不明"
                        })
                unique_formats = list({f['res']: f for f in sorted(formats, key=lambda x: x['height'], reverse=True)}.values())
                return jsonify({'type': 'video', 'title': info['title'], 'thumbnail': info['thumbnail'], 'formats': unique_formats, 'url': url})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/enqueue', methods=['POST'])
def enqueue():
    data = request.json
    task_id = f"task_{int(time.time() * 1000)}"
    download_queue.put((data['url'], data['mode'], data.get('format_id', 'best'), data['title'], task_id))
    return jsonify({'task_id': task_id, 'queue_size': download_queue.qsize()})

@app.route('/cancel', methods=['POST'])
def cancel():
    task_id = request.json.get('task_id')
    cancel_list.add(task_id)
    return jsonify({'status': 'canceled'})

@app.route('/get_file/<task_id>/<ext>/<title>')
def get_file(task_id, ext, title):
    path = os.path.join(DOWNLOAD_FOLDER, f"{task_id}.{ext}")
    return send_file(path, as_attachment=True, download_name=f"{title}.{ext}")

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    # Web公開時は debug=False にするのが安全です
    socketio.run(app, host='0.0.0.0', port=port, debug=False)