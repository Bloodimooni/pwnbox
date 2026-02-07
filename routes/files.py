import os
import uuid
import mimetypes
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, \
    current_app, send_from_directory
from database import get_db
from routes.auth import login_required, log_event

files_bp = Blueprint('files', __name__)


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']


@files_bp.route('/')
@login_required
def index():
    db = get_db()
    files = db.execute(
        """SELECT f.*, u.username, u.display_name
           FROM files f
           JOIN users u ON f.uploaded_by = u.id
           ORDER BY f.created_at DESC"""
    ).fetchall()
    return render_template('files/list.html', files=files)


@files_bp.route('/upload', methods=['POST'])
@login_required
def upload():
    if 'file' not in request.files:
        flash('No file selected.')
        return redirect(url_for('files.index'))

    file = request.files['file']
    if not file or not file.filename:
        flash('No file selected.')
        return redirect(url_for('files.index'))

    if not allowed_file(file.filename):
        flash('File type not allowed.')
        return redirect(url_for('files.index'))

    original_filename = file.filename
    ext = original_filename.rsplit('.', 1)[1].lower()
    stored_filename = f"{uuid.uuid4().hex}.{ext}"
    upload_path = os.path.join(current_app.config['UPLOAD_FOLDER'], stored_filename)
    file.save(upload_path)

    file_size = os.path.getsize(upload_path)
    mime_type = mimetypes.guess_type(original_filename)[0] or 'application/octet-stream'

    channel_id = request.form.get('channel_id')
    if channel_id:
        channel_id = int(channel_id)

    db = get_db()
    db.execute(
        """INSERT INTO files (filename, stored_filename, file_size, mime_type, uploaded_by, channel_id)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (original_filename, stored_filename, file_size, mime_type, session['user_id'], channel_id)
    )
    db.commit()

    log_event('file_upload', session['user_id'], {'filename': original_filename})
    flash('File uploaded successfully.')
    return redirect(url_for('files.index'))


@files_bp.route('/download/<int:file_id>')
@login_required
def download(file_id):
    db = get_db()
    file_record = db.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()

    if not file_record:
        flash('File not found.')
        return redirect(url_for('files.index'))

    log_event('file_download', session['user_id'], {'file_id': file_id, 'filename': file_record['filename']})
    return send_from_directory(
        current_app.config['UPLOAD_FOLDER'],
        file_record['stored_filename'],
        download_name=file_record['filename'],
        as_attachment=True
    )


@files_bp.route('/view/<int:file_id>')
@login_required
def view(file_id):
    db = get_db()
    file_record = db.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()

    if not file_record:
        flash('File not found.')
        return redirect(url_for('files.index'))

    return send_from_directory(
        current_app.config['UPLOAD_FOLDER'],
        file_record['stored_filename'],
        mimetype=file_record['mime_type']
    )


@files_bp.route('/delete/<int:file_id>', methods=['POST'])
@login_required
def delete(file_id):
    db = get_db()
    file_record = db.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()

    if not file_record:
        flash('File not found.')
        return redirect(url_for('files.index'))

    if file_record['uploaded_by'] != session['user_id']:
        flash('You can only delete your own files.')
        return redirect(url_for('files.index'))

    file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], file_record['stored_filename'])
    if os.path.exists(file_path):
        os.remove(file_path)

    db.execute("DELETE FROM files WHERE id = ?", (file_id,))
    db.commit()

    log_event('file_delete', session['user_id'], {'file_id': file_id, 'filename': file_record['filename']})
    flash('File deleted.')
    return redirect(url_for('files.index'))
