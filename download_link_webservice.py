from flask import Flask, request, send_file, abort, render_template, send_from_directory
import sqlite3
import os

app = Flask(__name__)
BASE_DIR = 'uploads'
DB_FILE = 'database.db'

@app.route('/download')
def download():
    token = request.args.get('token')
    if not token:
        return "Invalid token", 400

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT filename, user_id FROM files WHERE download_token=?", (token,))
    result = c.fetchone()
    if not result:
        conn.close()
        return "file has been deleted or token has been expired. please try again", 404

    filename, user_id = result
    file_path = os.path.join(BASE_DIR, str(user_id), filename)

    c.execute("UPDATE files SET download_token=NULL WHERE download_token=?", (token,))
    conn.commit()
    conn.close()

    if not os.path.isfile(file_path):
        return "file not found", 404

    return send_file(file_path, as_attachment=True)

@app.route('/watch/<int:user_id>/<filename>')
def watch(user_id, filename):
    if not user_id or not filename:
        return "Missing parameters", 400

    file_path = os.path.join(BASE_DIR, str(user_id), filename)
    if not os.path.isfile(file_path):
        return "Video not found", 404
    
    video_url = f"/uploads/{user_id}/{filename}"
    return render_template("watch.html", video_url=video_url)

@app.route('/uploads/<int:user_id>/<filename>')
def uploaded_file(user_id, filename):
    directory = os.path.join(BASE_DIR, str(user_id))
    return send_from_directory(directory, filename)

if __name__ == '__main__':
    app.run(host='HOST', port=8002)
