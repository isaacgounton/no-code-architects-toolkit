from flask import Flask, request, jsonify
from flask_login import LoginManager
from flask_migrate import Migrate
from models import db, User, APIKey
from queue import Queue # Added import
import threading
import uuid
import os
import time
from functools import wraps
from version import BUILD_NUMBER
from app_utils import log_job_status
import importlib
# from services.webhook import send_webhook # Will be imported locally in process_queue

MAX_QUEUE_LENGTH = int(os.environ.get('MAX_QUEUE_LENGTH', 0))

def create_app():
    app = Flask(__name__, template_folder='templates')
    
    # Configure SQLAlchemy and other settings
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-change-in-production')
    
    # Initialize extensions
    db.init_app(app)
    migrate = Migrate(app, db)
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'web_auth.login'
    
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Create database tables
    with app.app_context():
        db.create_all()

    # Create a queue to hold tasks
    task_queue = Queue()
    queue_id = id(task_queue)

    # Queue processing function
    def process_queue():
        while True:
            job_id, data, task_func, queue_start_time = task_queue.get()
            queue_time = time.time() - queue_start_time
            run_start_time = time.time()
            pid = os.getpid()
            
            log_job_status(job_id, {
                "job_status": "running",
                "job_id": job_id,
                "queue_id": queue_id,
                "process_id": pid,
                "response": None
            })
            
            response = task_func() # This is where the actual route function is called
            run_time = time.time() - run_start_time
            total_time = time.time() - queue_start_time

            response_data = {
                "endpoint": response[1] if isinstance(response, tuple) and len(response) > 1 else "unknown_endpoint", # Safely access endpoint
                "code": response[2] if isinstance(response, tuple) and len(response) > 2 else 500, # Safely access code
                "id": data.get("id"),
                "job_id": job_id,
                "response": response[0] if isinstance(response, tuple) and len(response) > 0 and response[2] == 200 else None,
                "message": "success" if isinstance(response, tuple) and len(response) > 2 and response[2] == 200 else (response[0] if isinstance(response, tuple) and len(response) > 0 else "error"),
                "pid": pid,
                "queue_id": queue_id,
                "run_time": round(run_time, 3),
                "queue_time": round(queue_time, 3),
                "total_time": round(total_time, 3),
                "queue_length": task_queue.qsize(),
                "build_number": BUILD_NUMBER
            }
            
            log_job_status(job_id, {
                "job_status": "done",
                "job_id": job_id,
                "queue_id": queue_id,
                "process_id": pid,
                "response": response_data
            })

            if data.get("webhook_url") and data.get("webhook_url") != "":
                from services.webhook import send_webhook # Import here
                send_webhook(data.get("webhook_url"), response_data)

            task_queue.task_done()

    # Start queue processing thread
    threading.Thread(target=process_queue, daemon=True).start()

    # Queue task decorator
    def queue_task(bypass_queue=False):
        def decorator(f):
            @wraps(f)
            def wrapper(*args, **kwargs):
                # API key verification logic
                # Exclude web routes and static files from API key check
                # Check if current endpoint is not for static files and not part of web_auth blueprint
                if not request.path.startswith('/static') and \
                   (not request.blueprint or request.blueprint != 'web_auth') and \
                   request.endpoint != 'static':
                    
                    api_key_value = request.headers.get('X-API-Key')
                    if not api_key_value:
                            return jsonify({"message": "API key is missing"}), 401

                    api_key_obj = APIKey.query.filter_by(key=api_key_value, revoked=False).first()
                    
                    if not api_key_obj or not api_key_obj.is_valid():
                        return jsonify({"message": "Unauthorized - Invalid or revoked API key"}), 401
                    
                    from datetime import datetime
                    api_key_obj.last_used_at = datetime.utcnow()
                    db.session.commit()

                job_id = str(uuid.uuid4())
                data = request.json if request.is_json else {}
                pid = os.getpid()
                start_time = time.time()
                
                if bypass_queue or 'webhook_url' not in data:
                    log_job_status(job_id, {"job_status": "running", "job_id": job_id, "queue_id": queue_id, "process_id": pid, "response": None})
                    response_tuple = f(job_id=job_id, data=data, *args, **kwargs) # Route function must return a 3-tuple
                    run_time = time.time() - start_time

                    response_content, endpoint_name, status_code = response_tuple

                    response_obj = {
                        "code": status_code, "id": data.get("id"), "job_id": job_id,
                        "response": response_content if status_code == 200 else None,
                        "message": "success" if status_code == 200 else response_content,
                        "run_time": round(run_time, 3), "queue_time": 0, "total_time": round(run_time, 3),
                        "pid": pid, "queue_id": queue_id, "queue_length": task_queue.qsize(), "build_number": BUILD_NUMBER
                    }
                    log_job_status(job_id, {"job_status": "done", "job_id": job_id, "queue_id": queue_id, "process_id": pid, "response": response_obj})
                    return response_obj, status_code
                else: # Queued task
                    if MAX_QUEUE_LENGTH > 0 and task_queue.qsize() >= MAX_QUEUE_LENGTH:
                        error_response = {
                            "code": 429, "id": data.get("id"), "job_id": job_id,
                            "message": f"MAX_QUEUE_LENGTH ({MAX_QUEUE_LENGTH}) reached",
                            "pid": pid, "queue_id": queue_id, "queue_length": task_queue.qsize(), "build_number": BUILD_NUMBER
                        }
                        log_job_status(job_id, {"job_status": "done", "job_id": job_id, "queue_id": queue_id, "process_id": pid, "response": error_response})
                        return error_response, 429
                    
                    log_job_status(job_id, {"job_status": "queued", "job_id": job_id, "queue_id": queue_id, "process_id": pid, "response": None})
                    task_queue.put((job_id, data, lambda: f(job_id=job_id, data=data, *args, **kwargs), start_time))
                    return {
                        "code": 202, "id": data.get("id"), "job_id": job_id, "message": "processing",
                        "pid": pid, "queue_id": queue_id, "max_queue_length": MAX_QUEUE_LENGTH if MAX_QUEUE_LENGTH > 0 else "unlimited",
                        "queue_length": task_queue.qsize(), "build_number": BUILD_NUMBER
                    }, 202
            return wrapper
        return decorator

    app.queue_task = queue_task # Make decorator available on app object

    # Import and register web interface blueprints
    from routes.web.auth import web_auth_bp
    app.register_blueprint(web_auth_bp)

    # Import and register API blueprints
    from routes.media_to_mp3 import convert_bp
    from routes.transcribe_media import transcribe_bp
    from routes.combine_videos import combine_bp
    from routes.audio_mixing import audio_mixing_bp
    from routes.gdrive_upload import gdrive_upload_bp
    from routes.authenticate import auth_bp
    from routes.caption_video import caption_bp
    from routes.extract_keyframes import extract_keyframes_bp
    from routes.image_to_video import image_to_video_bp

    # Register API blueprints
    app.register_blueprint(convert_bp)
    app.register_blueprint(transcribe_bp)
    app.register_blueprint(combine_bp)
    app.register_blueprint(audio_mixing_bp)
    app.register_blueprint(gdrive_upload_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(caption_bp)
    app.register_blueprint(extract_keyframes_bp)
    app.register_blueprint(image_to_video_bp)

    # Import and register v1.0 API blueprints
    from routes.v1.ffmpeg.ffmpeg_compose import v1_ffmpeg_compose_bp
    from routes.v1.media.media_transcribe import v1_media_transcribe_bp
    from routes.v1.media.feedback import v1_media_feedback_bp
    from routes.v1.media.convert.media_to_mp3 import v1_media_convert_mp3_bp
    from routes.v1.video.concatenate import v1_video_concatenate_bp
    from routes.v1.video.caption_video import v1_video_caption_bp
    from routes.v1.image.convert.image_to_video import v1_image_convert_video_bp
    from routes.v1.toolkit.test import v1_toolkit_test_bp
    from routes.v1.toolkit.authenticate import v1_toolkit_auth_bp
    from routes.v1.code.execute.execute_python import v1_code_execute_bp
    from routes.v1.s3.upload import v1_s3_upload_bp
    from routes.v1.video.thumbnail import v1_video_thumbnail_bp
    from routes.v1.media.download import v1_media_download_bp
    from routes.v1.media.convert.media_convert import v1_media_convert_bp
    from routes.v1.audio.concatenate import v1_audio_concatenate_bp
    from routes.v1.media.silence import v1_media_silence_bp
    from routes.v1.video.cut import v1_video_cut_bp
    from routes.v1.video.split import v1_video_split_bp
    from routes.v1.video.trim import v1_video_trim_bp
    from routes.v1.media.metadata import v1_media_metadata_bp
    from routes.v1.toolkit.job_status import v1_toolkit_job_status_bp
    from routes.v1.toolkit.jobs_status import v1_toolkit_jobs_status_bp
    from routes.v1.audio.speech import v1_audio_speech_bp
    from routes.v1.media.media_duration import v1_media_duration_bp

    # Register v1.0 API blueprints
    app.register_blueprint(v1_ffmpeg_compose_bp)
    app.register_blueprint(v1_media_transcribe_bp)
    app.register_blueprint(v1_media_feedback_bp)
    app.register_blueprint(v1_media_convert_mp3_bp)
    app.register_blueprint(v1_video_concatenate_bp)
    app.register_blueprint(v1_video_caption_bp)
    app.register_blueprint(v1_image_convert_video_bp)
    app.register_blueprint(v1_toolkit_test_bp)
    app.register_blueprint(v1_toolkit_auth_bp)
    app.register_blueprint(v1_code_execute_bp)
    app.register_blueprint(v1_s3_upload_bp)
    app.register_blueprint(v1_video_thumbnail_bp)
    app.register_blueprint(v1_media_download_bp)
    app.register_blueprint(v1_media_convert_bp)
    app.register_blueprint(v1_audio_concatenate_bp)
    app.register_blueprint(v1_media_silence_bp)
    app.register_blueprint(v1_video_cut_bp)
    app.register_blueprint(v1_video_split_bp)
    app.register_blueprint(v1_video_trim_bp)
    app.register_blueprint(v1_media_metadata_bp)
    app.register_blueprint(v1_toolkit_job_status_bp)
    app.register_blueprint(v1_toolkit_jobs_status_bp)
    app.register_blueprint(v1_audio_speech_bp)
    app.register_blueprint(v1_media_duration_bp)

    # Register Next.js root asset paths
    from routes.v1.media.feedback import create_root_next_routes
    create_root_next_routes(app)

    return app

app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
