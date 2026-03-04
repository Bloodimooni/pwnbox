import os
import uuid
import mimetypes
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, \
    current_app, send_from_directory
from database import get_db
from routes.auth import login_required, full_access_required, log_event

files_bp = Blueprint('files', __name__)


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']


def check_file_access(file_record, user_id):
    """Check if a user can access a file.
    DM attachments are restricted to conversation participants.
    Channel attachments and file manager uploads are accessible to all logged-in users.
    """
    if file_record['conversation_id']:
        db = get_db()
        conv = db.execute(
            "SELECT id FROM dm_conversations WHERE id = ? AND (user1_id = ? OR user2_id = ?)",
            (file_record['conversation_id'], user_id, user_id)
        ).fetchone()
        return conv is not None
    return True


@files_bp.route('/')
@full_access_required
def index():
    db = get_db()
    db_files = db.execute(
        """SELECT f.*, u.username, u.display_name
           FROM files f
           JOIN users u ON f.uploaded_by = u.id
           WHERE f.channel_id IS NULL AND f.conversation_id IS NULL
           ORDER BY f.created_at DESC"""
    ).fetchall()

    # Convert DB rows to plain dicts and mark as registered.
    all_files = [{**dict(f), 'fs_only': False} for f in db_files]

    # Also surface files physically present in the uploads root that aren't in the DB.
    # This lets a CTF player move a file there from a reverse shell and see it immediately,
    # without needing to register it through the normal upload flow.
    upload_folder = current_app.config['UPLOAD_FOLDER']
    db_stored = {f['stored_filename'] for f in db_files}
    try:
        for fname in sorted(os.listdir(upload_folder)):
            fpath = os.path.join(upload_folder, fname)
            if os.path.isfile(fpath) and not fname.startswith('.') and fname not in db_stored:
                all_files.append({
                    'id': None,
                    'filename': fname,
                    'stored_filename': fname,
                    'file_size': os.path.getsize(fpath),
                    'mime_type': mimetypes.guess_type(fname)[0] or 'application/octet-stream',
                    'username': 'system',
                    'display_name': 'system',
                    'created_at': None,
                    'is_encrypted': False,
                    'uploaded_by': None,
                    'fs_only': True,
                })
    except OSError:
        pass

    return render_template('files/list.html', files=all_files)


@files_bp.route('/upload', methods=['POST'])
@full_access_required
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
@full_access_required
def download(file_id):
    db = get_db()
    file_record = db.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()

    if not file_record:
        flash('File not found.')
        return redirect(url_for('files.index'))

    if not check_file_access(file_record, session['user_id']):
        flash('Access denied.')
        return redirect(url_for('files.index'))

    log_event('file_download', session['user_id'], {'file_id': file_id, 'filename': file_record['filename']})
    return send_from_directory(
        current_app.config['UPLOAD_FOLDER'],
        file_record['stored_filename'],
        download_name=file_record['filename'],
        as_attachment=True
    )


@files_bp.route('/download-raw/<path:filename>')
@login_required
def download_raw(filename):
    """Download a file from the uploads root by name (no DB registration required).
    Used for files that appear via filesystem scan in the index view.
    """
    safe_name = os.path.basename(filename)
    upload_folder = current_app.config['UPLOAD_FOLDER']
    fpath = os.path.join(upload_folder, safe_name)
    if not os.path.isfile(fpath):
        flash('File not found.')
        return redirect(url_for('files.index'))
    log_event('file_download_raw', session['user_id'], {'filename': safe_name})
    return send_from_directory(upload_folder, safe_name, as_attachment=True)


@files_bp.route('/view/<int:file_id>')
@full_access_required
def view(file_id):
    db = get_db()
    file_record = db.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()

    if not file_record:
        flash('File not found.')
        return redirect(url_for('files.index'))

    if not check_file_access(file_record, session['user_id']):
        flash('Access denied.')
        return redirect(url_for('files.index'))

    return send_from_directory(
        current_app.config['UPLOAD_FOLDER'],
        file_record['stored_filename'],
        mimetype=file_record['mime_type']
    )


@files_bp.route('/delete/<int:file_id>', methods=['POST'])
@full_access_required
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
