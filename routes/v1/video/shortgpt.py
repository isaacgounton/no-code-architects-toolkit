from flask import Blueprint, request, jsonify, current_app
from services.v1.video.shortgpt_service import ShortGPTService
import uuid

shortgpt_bp = Blueprint('shortgpt', __name__, url_prefix='/v1/video/shortgpt')
shortgpt_service = ShortGPTService()

@shortgpt_bp.route('', methods=['POST'])
@current_app.queue_task()  # Use the queue decorator from app.py
async def create_short_video(job_id=None, data=None):
    """
    Create a video using ShortGPT
    
    Request Body:
    {
        "engine_type": "content" | "translation" | "facts",
        "script": "Text script for content engine",
        "source_url": "URL for translation engine",
        "facts_type": "Topic for facts engine",
        "language": "EN",
        "voice_gender": "male" | "female",
        "watermark": "Optional watermark text",
        "vertical": false,
        "use_captions": false,
        "background_music_url": "Optional music URL",
        "background_video_url": "Optional video URL",
        "num_images": 5
    }
    """
    try:
        # Use data from queue_task decorator or request
        request_data = data if data else request.get_json()
        
        # Validate required fields based on engine type
        engine_type = request_data.get('engine_type', 'content').lower()
        
        if engine_type == 'content' and 'script' not in request_data:
            return jsonify({
                'status': 'error',
                'message': 'script is required for content engine'
            }), 400, 'VALIDATION_ERROR'
            
        elif engine_type == 'translation' and 'source_url' not in request_data:
            return jsonify({
                'status': 'error',
                'message': 'source_url is required for translation engine'
            }), 400, 'VALIDATION_ERROR'
            
        elif engine_type == 'facts' and 'facts_type' not in request_data:
            return jsonify({
                'status': 'error',
                'message': 'facts_type is required for facts engine'
            }), 400, 'VALIDATION_ERROR'

        # Generate job_id if not provided by queue
        if not job_id:
            job_id = str(uuid.uuid4())

        # Process video creation
        result = await shortgpt_service.create_short_video(request_data, job_id)

        if result['status'] == 'error':
            return jsonify({
                'status': 'error',
                'message': result['message']
            }), 500, 'VIDEO_GENERATION_ERROR'

        # Return successful response with video URL
        response = {
            'status': 'success',
            'video_url': result['video_url'],
            'message': result['message'],
            'job_id': result['job_id'],
            'engine_type': result['engine_type']
        }

        # Include additional information if available
        if 'steps' in result:
            response['steps'] = result['steps']

        return response, 200, 'SUCCESS'

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500, 'INTERNAL_ERROR'
