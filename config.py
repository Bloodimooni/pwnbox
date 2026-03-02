import os

_basedir = os.path.dirname(__file__)


class BaseConfig:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'rSJhjbPT3zuVzffVtb3XuvnrCv39CZq8')
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10 MB
    ALLOWED_EXTENSIONS = {
        'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'zip', 'doc', 'docx',
        'mp4', 'mp3', 'webm', 'ogg', 'wav', 'mov', 'avi',
        'svg', 'webp', 'csv', 'json', 'xml', 'pptx', 'xlsx', 'sh', 'py',
    }
    CRYPTO_SIGNING_KEY = os.environ.get('CRYPTO_KEY', 'rSJhjbPT3zuVzffVtb3XuvnrCv39CZq8')
    APP_VERSION = '1.0.0'


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    DATABASE_DIR = os.environ.get('DATABASE_DIR', os.path.join(_basedir, 'data'))
    DATABASE_PATH = os.path.join(
        os.environ.get('DATABASE_DIR', os.path.join(_basedir, 'data')), 'corpchat.db'
    )
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', os.path.join(_basedir, 'uploads'))
    LOG_DIR = os.environ.get('LOG_DIR', os.path.join(_basedir, 'logs'))
    BACKUP_DIR = os.environ.get('BACKUP_DIR', os.path.join(_basedir, 'data', 'backups'))


class ProductionConfig(BaseConfig):
    DEBUG = False
    DATABASE_DIR = os.environ.get('DATABASE_DIR', '/data')
    DATABASE_PATH = os.path.join(
        os.environ.get('DATABASE_DIR', '/data'), 'corpchat.db'
    )
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', '/data/uploads')
    LOG_DIR = os.environ.get('LOG_DIR', '/data/logs')
    BACKUP_DIR = os.environ.get('BACKUP_DIR', '/data/backups')
