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



from flask import Blueprint, current_app # Added current_app
from app_utils import validate_payload # Keep validate_payload, remove *
import logging
import os
from services.v1.media.media_transcribe import process_transcribe_media
# from services.authentication import authenticate # Removed
from services.cloud_storage import upload_file

v1_media_transcribe_bp = Blueprint('v1_media_transcribe', __name__)
logger = logging.getLogger(__name__)

@v1_media_transcribe_bp.route('/v1/media/transcribe', methods=['POST'])
# @authenticate # Removed
@validate_payload({
    "type": "object",
    "properties": {
        "media_url": {"type": "string", "format": "uri"},
        "task": {"type": "string", "enum": ["transcribe", "translate"]},
        "include_text": {"type": "boolean"},
        "include_srt": {"type": "boolean"},
        "include_segments": {"type": "boolean"},
        "word_timestamps": {"type": "boolean"},
        "response_type": {"type": "string", "enum": ["direct", "cloud"]},
        "language": {"type": "string"},
        "webhook_url": {"type": "string", "format": "uri"},
        "id": {"type": "string"},
        "words_per_line": {"type": "integer", "minimum": 1}
    },
    "required": ["media_url"],
    "additionalProperties": False
})
@current_app.queue_task(bypass_queue=False) # Changed decorator
def transcribe(job_id, data):
    # The API key check is now handled by the @current_app.queue_task decorator
    # Get the validated and type-converted data
    validated_data = getattr(request, '_validated_json', request.json)
    media_url = validated_data['media_url']
    task = validated_data.get('task', 'transcribe')
    include_text = validated_data.get('include_text', True)
    include_srt = validated_data.get('include_srt', False)
    include_segments = validated_data.get('include_segments', False)
    word_timestamps = validated_data.get('word_timestamps', False)
    response_type = validated_data.get('response_type', 'direct')
    language = validated_data.get('language', None)
    webhook_url = validated_data.get('webhook_url')
    id = validated_data.get('id')
    words_per_line = validated_data.get('words_per_line', None)

    logger.info(f"Job {job_id}: Received transcription request for {media_url}")

    try:
        result = process_transcribe_media(media_url, task, include_text, include_srt, include_segments, word_timestamps, response_type, language, job_id, words_per_line)
        logger.info(f"Job {job_id}: Transcription process completed successfully")

        # If the result is a file path, upload it using the unified upload_file() method
        if response_type == "direct":
           
            result_json = {
                "text": result[0],
                "srt": result[1],
                "segments": result[2],
                "text_url": None,
                "srt_url": None,
                "segments_url": None,
            }

            return result_json, "/v1/transcribe/media", 200

        else:

            cloud_urls = {
                "text": None,
                "srt": None,
                "segments": None,
                "text_url": upload_file(result[0]) if include_text is True else None,
                "srt_url": upload_file(result[1]) if include_srt is True else None,
                "segments_url": upload_file(result[2]) if include_segments is True else None,
            }

            if include_text is True:
                os.remove(result[0])  # Remove the temporary file after uploading
            
            if include_srt is True:
                os.remove(result[1])

            if include_segments is True:
                os.remove(result[2])
            
            return cloud_urls, "/v1/transcribe/media", 200

    except Exception as e:
        logger.error(f"Job {job_id}: Error during transcription process - {str(e)}")
        return str(e), "/v1/transcribe/media", 500
