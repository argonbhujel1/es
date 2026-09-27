import cloudinary
import cloudinary.uploader
from flask import current_app
from werkzeug.utils import secure_filename
import uuid


def allowed_file(filename):
    if not filename:
        return False
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    return ext in current_app.config.get('ALLOWED_EXTENSIONS', {'png', 'jpg', 'jpeg', 'gif', 'webp'})


def upload_image(file, folder='esports_arena'):
    """Upload to Cloudinary or return None if not configured."""
    if not file or not file.filename:
        return None
    if not allowed_file(file.filename):
        raise ValueError('Invalid file type. Allowed: png, jpg, jpeg, gif, webp')

    # Check size roughly
    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    max_size = current_app.config.get('MAX_CONTENT_LENGTH', 5 * 1024 * 1024)
    if size > max_size:
        raise ValueError(f'File too large. Max {max_size // (1024*1024)}MB')

    cloud_name = current_app.config.get('CLOUDINARY_CLOUD_NAME')
    if cloud_name:
        result = cloudinary.uploader.upload(
            file,
            folder=folder,
            public_id=f'{uuid.uuid4().hex}',
            resource_type='image'
        )
        return result.get('secure_url')
    else:
        # Local fallback for development
        import os
        from flask import url_for
        upload_dir = os.path.join(current_app.root_path, 'static', 'uploads')
        os.makedirs(upload_dir, exist_ok=True)
        filename = f'{uuid.uuid4().hex}_{secure_filename(file.filename)}'
        path = os.path.join(upload_dir, filename)
        file.save(path)
        return f'/static/uploads/{filename}'
