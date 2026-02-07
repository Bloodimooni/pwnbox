# File Management

[Back to Index](README.md)

---

## Overview

PwnBox provides a file sharing system that supports both standalone file uploads (via the Files page) and inline attachments in chat/DM messages. Files are stored on the server filesystem with UUID-based names and tracked in the `files` database table.

- **Backend:** `routes/files.py` (web UI routes) and `routes/api.py` (API upload/list/view)
- **Frontend:** `templates/files/list.html`
- **Storage:** `uploads/` directory (development) or `/data/uploads` (production)

---

## Source File: `routes/files.py`

This file defines the `files_bp` blueprint with URL prefix `/files`.

### Helper: `allowed_file()` (lines 12-14)

```python
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']
```

Checks if a filename has an extension that's in the allowed set. The allowed extensions are configured in `config.py`:

```python
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'zip', 'doc', 'docx'}
```

---

### Route: `GET /files/` -- File Listing

**Function:** `index()` (lines 17-27)
**Decorator:** `@login_required`

Lists all uploaded files, sorted by most recent first.

**Query:**
```sql
SELECT f.*, u.username, u.display_name
FROM files f
JOIN users u ON f.uploaded_by = u.id
ORDER BY f.created_at DESC
```

Renders `files/list.html` with the file list.

---

### Route: `POST /files/upload` -- Upload File

**Function:** `upload()` (lines 30-69)
**Decorator:** `@login_required`

Handles file upload from the Files page modal.

**Step-by-step process:**

1. **Validate file presence:**
   - `'file'` must be in `request.files`
   - The file object must exist and have a filename
   - Flashes "No file selected." if missing

2. **Validate file type:**
   - Calls `allowed_file(file.filename)`
   - Flashes "File type not allowed." if invalid

3. **Generate storage name:**
   ```python
   ext = original_filename.rsplit('.', 1)[1].lower()
   stored_filename = f"{uuid.uuid4().hex}.{ext}"
   ```
   Example: `report.pdf` becomes `a1b2c3d4e5f6789012345678abcdef01.pdf`

4. **Save to disk:**
   ```python
   upload_path = os.path.join(current_app.config['UPLOAD_FOLDER'], stored_filename)
   file.save(upload_path)
   ```

5. **Get metadata:**
   ```python
   file_size = os.path.getsize(upload_path)
   mime_type = mimetypes.guess_type(original_filename)[0] or 'application/octet-stream'
   ```

6. **Insert database record:**
   ```sql
   INSERT INTO files (filename, stored_filename, file_size, mime_type, uploaded_by, channel_id)
   VALUES (?, ?, ?, ?, ?, ?)
   ```
   Note: `channel_id` comes from an optional form field.

7. **Log and redirect:**
   - Logs `file_upload` event with original filename
   - Flashes success message
   - Redirects to file listing

---

### Route: `GET /files/download/<int:file_id>` -- Download File

**Function:** `download()` (lines 72-88)
**Decorator:** `@login_required`

Downloads a file as an attachment (triggers browser download dialog).

1. Looks up the file record by ID
2. Logs `file_download` event
3. Uses Flask's `send_from_directory()`:
   ```python
   send_from_directory(
       current_app.config['UPLOAD_FOLDER'],
       file_record['stored_filename'],
       download_name=file_record['filename'],  # Original filename in download
       as_attachment=True
   )
   ```

The `download_name` parameter ensures the user sees the original filename, not the UUID-based storage name.

---

### Route: `GET /files/view/<int:file_id>` -- View File Inline

**Function:** `view()` (lines 91-105)
**Decorator:** `@login_required`

Serves the file for inline viewing (e.g., displaying images in chat messages).

```python
send_from_directory(
    current_app.config['UPLOAD_FOLDER'],
    file_record['stored_filename'],
    mimetype=file_record['mime_type']
)
```

Unlike download, this does **not** set `as_attachment=True`, so the browser will attempt to display the file inline (especially useful for images).

**Used by:** Chat and DM templates render attachments as `<img src="/files/view/{id}">`.

---

### Route: `POST /files/delete/<int:file_id>` -- Delete File

**Function:** `delete()` (lines 108-131)
**Decorator:** `@login_required`

Deletes a file from both disk and database.

**Authorization:** Only the uploader can delete their files:
```python
if file_record['uploaded_by'] != session['user_id']:
    flash('You can only delete your own files.')
    return redirect(url_for('files.index'))
```

**Process:**
1. Look up file record
2. Check ownership
3. Delete from filesystem: `os.remove(file_path)`
4. Delete database record: `DELETE FROM files WHERE id = ?`
5. Log `file_delete` event
6. Flash confirmation and redirect

---

## API Endpoints for Files

### `GET /api/v1/files` -- List All Files

**Function:** `list_files()` in `routes/api.py` (lines 259-270)
**Auth:** `@api_auth_required`

Returns all files as JSON:
```json
{
  "data": [
    {
      "id": 1,
      "filename": "photo.png",
      "file_size": 245760,
      "mime_type": "image/png",
      "created_at": "2026-02-07 12:00:00",
      "is_encrypted": 0,
      "uploaded_by_name": "demo"
    }
  ]
}
```

### `GET /api/v1/files/view/<file_id>`

This endpoint is **not explicitly defined** in the API. The frontend uses the web route `/files/view/<id>` directly for displaying attached images.

### Chat/DM Upload Endpoints

See [Chat System](chat-system.md) and [Direct Messaging](direct-messaging.md) for the channel/DM-specific upload endpoints at:
- `POST /api/v1/channels/<id>/upload`
- `POST /api/v1/dm/<id>/upload`

---

## Template: `templates/files/list.html`

Extends `base.html`.

### File List
Each file is displayed as a row with:
- **Filename** -- the original upload name
- **Metadata** -- uploader name, upload date, file size (in KB, rounded to 1 decimal)
- **Encryption badge** -- shown if `file.is_encrypted` is true (placeholder feature)
- **Download button** -- links to `/files/download/{id}`
- **Delete button** -- only shown if the current user uploaded the file; confirms with `confirm('Delete this file?')`

### Upload Modal
Triggered by the "Upload File" button. Contains:
- File input field
- Help text: "Allowed: txt, pdf, png, jpg, jpeg, gif, zip, doc, docx. Max 10MB."
- Cancel and Upload buttons
- Form POSTs to `/files/upload` with `enctype="multipart/form-data"`

---

## File Storage Strategy

### UUID Naming
Files on disk use UUID-based names:
```
uploads/
├── a1b2c3d4e5f6789012345678abcdef01.png
├── b2c3d4e5f6789012345678abcdef0102.pdf
└── c3d4e5f6789012345678abcdef010203.jpg
```

This provides:
- **No filename collisions** -- UUIDs are unique
- **No path traversal** -- filenames contain only hex characters and a single extension
- **Original name preservation** -- stored in the `filename` column for display/download

### Max Upload Size
Configured in `config.py`:
```python
MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10 MB
```
Flask enforces this at the framework level, rejecting requests with bodies larger than 10 MB before the route handler runs.

### Allowed Extensions
```python
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'zip', 'doc', 'docx'}
```

### MIME Type Detection
```python
mime_type = mimetypes.guess_type(original_filename)[0] or 'application/octet-stream'
```
Uses Python's `mimetypes` module to guess the MIME type from the original filename. Falls back to `application/octet-stream` if detection fails.
