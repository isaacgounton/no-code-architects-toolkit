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

from flask import Blueprint, jsonify
from app_utils import validate_payload, queue_task_wrapper
import logging
from services.v1.video.scripted_video import process_scripted_video_v1
from services.authentication import authenticate
from services.cloud_storage import upload_file
import os

v1_video_scripted_bp = Blueprint('v1_video/scripted', __name__)
logger = logging.getLogger(__name__)

@v1_video_scripted_bp.route('/v1/video/scripted', methods=['POST'])
@authenticate
@validate_payload({
    "type": "object",
    "properties": {
        "script": {"type": "string"},
        "tts": {
            "type": "string",
            "enum": ["edge-tts", "streamlabs-polly", "kokoro"],
            "default": "edge-tts"
        },
        "voice": {
            "type": "string"
        },
        "aspect_ratio": {
            "type": "string",
            "enum": ["16:9", "9:16", "1:1"],
            "default": "16:9"
        },
        "add_captions": {
            "type": "boolean",
            "default": False
        },
        "caption_settings": {
            "type": "object",
            "properties": {
                "style": {"type": "string"},
                "line_color": {"type": "string"},
                "word_color": {"type": "string"},
                "outline_color": {"type": "string"},
                "all_caps": {"type": "boolean"},
                "max_words_per_line": {"type": "integer"},
                "position": {"type": "string"},
                "alignment": {"type": "string"},
                "font_family": {"type": "string"},
                "font_size": {"type": "integer"},
                "bold": {"type": "boolean"},
                "italic": {"type": "boolean"}
            },
            "additionalProperties": False
        },
        "webhook_url": {"type": "string", "format": "uri"},
        "id": {"type": "string"},
        "use_placeholder": {"type": "boolean", "default": True},
        "placeholder_url": {"type": "string", "format": "uri"},
        "custom_media": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "scene_index": {"type": "integer", "minimum": 0},
                    "media_url": {"type": "string", "format": "uri"}
                },
                "required": ["scene_index", "media_url"],
                "additionalProperties": False
            }
        }
    },
    "required": ["script"],
    "additionalProperties": False
})
@queue_task_wrapper(bypass_queue=False)
def scripted_video_v1(job_id, data):
    """
    Generate a video from a script with voice synthesis and optional captions.
    """
    script = data['script']
    tts = data.get('tts', 'edge-tts')
    voice = data.get('voice')
    aspect_ratio = data.get('aspect_ratio', '16:9')
    add_captions = data.get('add_captions', False)
    caption_settings = data.get('caption_settings', {})
    webhook_url = data.get('webhook_url')
    request_id = data.get('id')

    logger.info(f"Job {job_id}: Received scripted video request")
    logger.info(f"Job {job_id}: Aspect ratio: {aspect_ratio}")
    logger.info(f"Job {job_id}: Voice: {voice}")
    logger.info(f"Job {job_id}: Add captions: {add_captions}")
    
    # Log new parameters
    use_placeholder = data.get('use_placeholder', True)
    placeholder_url = data.get('placeholder_url')
    custom_media = data.get('custom_media')
    
    if custom_media:
        logger.info(f"Job {job_id}: Using custom media for {len(custom_media)} scenes")
    if placeholder_url:
        logger.info(f"Job {job_id}: Using custom placeholder URL")
    logger.info(f"Job {job_id}: Use placeholder: {use_placeholder}")

    try:
        # Process video with all components
        output = process_scripted_video_v1(
            script=script,
            tts=tts,
            voice=voice,
            aspect_ratio=aspect_ratio,
            add_captions=add_captions,
            caption_settings=caption_settings,
            job_id=job_id,
            custom_media=custom_media,
            use_placeholder=use_placeholder,
            placeholder_url=placeholder_url
        )
        
        if isinstance(output, dict) and 'error' in output:
            return {"error": output['error']}, "/v1/video/scripted", 400

        # Output is the file path
        output_path = output
        logger.info(f"Job {job_id}: Video processing completed successfully")

        # Upload the final video
        cloud_url = upload_file(output_path)
        logger.info(f"Job {job_id}: Video uploaded to cloud storage: {cloud_url}")

        # Clean up the output file after upload
        os.remove(output_path)
        logger.info(f"Job {job_id}: Cleaned up local output file")

        return cloud_url, "/v1/video/scripted", 200

    except Exception as e:
        logger.error(f"Job {job_id}: Error during video processing - {str(e)}", exc_info=True)
        return {"error": str(e)}, "/v1/video/scripted", 500
