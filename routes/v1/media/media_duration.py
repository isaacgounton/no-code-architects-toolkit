from flask import Blueprint, request, current_app # Added current_app
from app_utils import validate_payload # Keep validate_payload, remove *
# from services.authentication import authenticate # Removed
from services.v1.media.media_duration import get_media_duration_from_url
import logging

v1_media_duration_bp = Blueprint("v1_media_duration_bp", __name__)
logger = logging.getLogger(__name__)

@v1_media_duration_bp.route("/v1/media/media-duration", methods=["POST"])
# @authenticate # Removed
@validate_payload(
    {
        "type": "object",
        "properties": {
            "media_url": {"type": "string", "format": "uri"},
            "webhook_url": {"type": "string", "format": "uri"},
            "id": {"type": "string"}
        },
        "required": ["media_url"],
        "additionalProperties": False
    }
)
@current_app.queue_task(bypass_queue=False) # Changed decorator
def get_media_duration(job_id, data):
    # The API key check is now handled by the @current_app.queue_task decorator
    # Get the validated and type-converted data
    validated_data = getattr(request, '_validated_json', request.json)
    media_url = validated_data['media_url']
    
    try:
        logger.info(f"Job {job_id}: Received media duration request for {media_url}")
        duration = get_media_duration_from_url(media_url)
        logger.info(f"Job {job_id}: media duration is {duration} seconds")
        return duration, "/v1/media/media-duration", 200
    except Exception as e:
        logger.exception(f"Job {job_id}: Exception - {str(e)}")
        return str(e), "/v1/media/media-duration", 500
