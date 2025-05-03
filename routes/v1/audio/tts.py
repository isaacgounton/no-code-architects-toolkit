from flask import Blueprint
from app_utils import *
import logging
from services.v1.audio.tts import list_voices, generate_speech
from services.authentication import authenticate
from services.cloud_storage import upload_file

v1_audio_tts_bp = Blueprint('v1_audio_tts', __name__)
logger = logging.getLogger(__name__)

@v1_audio_tts_bp.route('/v1/audio/tts/voices', methods=['GET'])
@authenticate
def get_voices():
    """List available voices for text-to-speech"""
    try:
        voices = list_voices()
        logger.info(f"Successfully retrieved {len(voices)} TTS voices")
        return {'voices': voices}, "/v1/audio/tts/voices", 200
    except Exception as e:
        logger.error(f"Error listing TTS voices: {str(e)}")
        return str(e), "/v1/audio/tts/voices", 500

@v1_audio_tts_bp.route('/v1/audio/tts/generate', methods=['POST'])
@authenticate
@validate_payload({
    "type": "object",
    "properties": {
        "text": {"type": "string", "minLength": 1},
        "voice": {"type": "string", "minLength": 1},
        "rate": {"type": "string", "pattern": "^[+-]\\d+%$"},  # e.g. "+50%", "-20%"
        "volume": {"type": "string", "pattern": "^[+-]\\d+%$"},  # e.g. "+50%", "-20%"
        "pitch": {"type": "string", "pattern": "^[+-]\\d+Hz$"},  # e.g. "+50Hz", "-20Hz"
        "webhook_url": {"type": "string", "format": "uri"},
        "id": {"type": "string"}
    },
    "required": ["text", "voice"],
    "additionalProperties": False
})
@queue_task_wrapper(bypass_queue=False)
def generate(job_id, data):
    """Generate speech from text"""
    try:
        text = data['text']
        voice = data['voice']
        rate = data.get('rate')
        volume = data.get('volume')
        pitch = data.get('pitch')
        
        logger.info(f"Job {job_id}: Received TTS request for voice '{voice}' with {len(text)} characters")
        if rate or volume or pitch:
            logger.info(f"Job {job_id}: Using adjustments - rate: {rate}, volume: {volume}, pitch: {pitch}")

        # Generate speech files
        audio_file, subtitle_file = generate_speech(
            text=text,
            voice=voice,
            job_id=job_id,
            rate=rate,
            volume=volume,
            pitch=pitch
        )
        logger.info(f"Job {job_id}: TTS generation completed successfully")

        # Upload files to cloud storage
        audio_url = upload_file(audio_file)
        subtitle_url = upload_file(subtitle_file)
        logger.info(f"Job {job_id}: Files uploaded to cloud storage")

        return {
            'audio_url': audio_url,
            'subtitle_url': subtitle_url
        }, "/v1/audio/tts/generate", 200

    except Exception as e:
        logger.error(f"Job {job_id}: Error during TTS generation - {str(e)}")
        return str(e), "/v1/audio/tts/generate", 500
