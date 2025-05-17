# Copyright (c) 2025 Stephen G. Pope
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

###########################################################################


# Author: Harrison Fisher (https://github.com/HarrisonFisher)
# Date: May 2025
# Created new route: /v1/audio/speech

from flask import Blueprint
from app_utils import validate_payload, queue_task_wrapper
import logging
from services.authentication import authenticate
from services.cloud_storage import upload_file
from services.v1.audio.speech import generate_tts, list_voices
import os

v1_audio_speech_bp = Blueprint("v1_audio_speech", __name__)
logger = logging.getLogger(__name__)

@v1_audio_speech_bp.route("/v1/audio/speech/voices", methods=["GET"])
@queue_task_wrapper(bypass_queue=True)  # This decorator should be innermost
@authenticate
def get_voices():
    """List available voices for text-to-speech"""
    try:
        voices = list_voices()
        logger.info(f"Successfully retrieved {len(voices)} TTS voices")
        return {'voices': voices}, "/v1/audio/speech/voices", 200
    except Exception as e:
        logger.error(f"Error listing TTS voices: {str(e)}")
        return str(e), "/v1/audio/speech/voices", 500

@v1_audio_speech_bp.route("/v1/audio/speech", methods=["POST"])
@authenticate
@validate_payload({
    "type": "object",
    "properties": {
        "tts": {"type": "string", "enum": ["edge-tts", "streamlabs-polly", "kokoro"]},
        "text": {"type": "string"},
        "voice": {"type": "string"},
        "rate": {"type": "string", "pattern": "^[+-]\\d+%$"},
        "volume": {"type": "string", "pattern": "^[+-]\\d+%$"},
        "pitch": {"type": "string", "pattern": "^[+-]\\d+Hz$"},
        "webhook_url": {"type": "string", "format": "uri"},
        "id": {"type": "string"},
        "output_format": {"type": "string", "enum": ["mp3", "wav"], "default": "mp3"}
    },
    "required": ["text"],
    "additionalProperties": False
})
@queue_task_wrapper(bypass_queue=False)
def text_to_speech(job_id, data):
    tts = data.get("tts", "edge-tts")
    text = data["text"]
    voice = data.get("voice")
    output_format = data.get("output_format", "mp3") # Get output_format, default to mp3
    rate = data.get("rate")
    volume = data.get("volume")
    pitch = data.get("pitch")
    webhook_url = data.get("webhook_url")
    id = data.get("id")

    logger.info(f"Job {job_id}: Received TTS request for text length {len(text)}")
    if rate or volume or pitch:
        logger.info(f"Job {job_id}: Using adjustments - rate: {rate}, volume: {volume}, pitch: {pitch}")

    try:
        audio_file, subtitle_file = generate_tts(
            tts=tts,
            text=text,
            voice=voice,
            job_id=job_id,
            output_format=output_format, # Pass output_format
            rate=rate,
            volume=volume,
            pitch=pitch
        )
        
        # Upload files to cloud storage
        audio_url = upload_file(audio_file)
        subtitle_url = upload_file(subtitle_file)
        
        logger.info(f"Job {job_id}: Files uploaded to cloud storage")
        return {
            'audio_url': audio_url,
            'subtitle_url': subtitle_url
        }, "/v1/audio/speech", 200
    except Exception as e:
        logger.error(f"Job {job_id}: Error during TTS process - {str(e)}")
        return str(e), "/v1/audio/speech", 500
    finally:
        try:
            if os.path.exists(audio_file):
                os.remove(audio_file)
            if os.path.exists(subtitle_file):
                os.remove(subtitle_file)
        except Exception as cleanup_error:
            logger.warning(f"Cleanup failed: {cleanup_error}")
