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
import time
from services.v1.video.scripted_video import process_scripted_video_v1, get_media_duration
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
    Enhanced with improved error handling, validation, and response formatting.
    """
    script = data['script']
    tts = data.get('tts', 'edge-tts')
    voice = data.get('voice')
    aspect_ratio = data.get('aspect_ratio', '16:9')
    add_captions = data.get('add_captions', False)
    caption_settings = data.get('caption_settings', {})
    webhook_url = data.get('webhook_url')
    request_id = data.get('id')
    
    # Get optional parameters with defaults
    use_placeholder = data.get('use_placeholder', True)
    placeholder_url = data.get('placeholder_url')
    custom_media = data.get('custom_media')
    
    # Log job parameters for tracking and debugging
    logger.info(f"Job {job_id}: Received scripted video request" + 
                (f" with id '{request_id}'" if request_id else ""))
    logger.info(f"Job {job_id}: Script length: {len(script)} chars, paragraph count: {script.count('\\n\\n')+1}")
    logger.info(f"Job {job_id}: TTS: {tts}, Voice: {voice}, Aspect ratio: {aspect_ratio}")
    logger.info(f"Job {job_id}: Add captions: {add_captions}")
    
    if custom_media:
        logger.info(f"Job {job_id}: Using custom media for {len(custom_media)} scenes")
    if placeholder_url:
        logger.info(f"Job {job_id}: Using custom placeholder URL")
    logger.info(f"Job {job_id}: Use placeholder: {use_placeholder}")

    # Track video processing time
    start_time = time.time()
    output_path = None
    
    try:
        # Validate essential parameters
        if not script.strip():
            return {"error": "Script cannot be empty"}, "/v1/video/scripted", 400
        
        # Check if script is too long
        if len(script) > 20000:  # Approximate limit ~3000 words
            return {"error": "Script is too long. Maximum length is approximately 3000 words."}, "/v1/video/scripted", 400
            
        # Validate voice parameter
        if tts != "edge-tts" and not voice:
            return {"error": "Voice parameter is required when not using edge-tts"}, "/v1/video/scripted", 400
            
        # Validate caption settings if provided
        if add_captions and caption_settings:
            if 'line_color' in caption_settings and not caption_settings['line_color'].startswith('#'):
                return {"error": "Invalid line_color format. Must be a hex color code starting with #"}, "/v1/video/scripted", 400
                
            if 'font_size' in caption_settings and (caption_settings['font_size'] < 12 or caption_settings['font_size'] > 72):
                return {"error": "Invalid font_size. Must be between 12 and 72"}, "/v1/video/scripted", 400
        
        # Process video with all components
        try:
            output_path = process_scripted_video_v1(
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
        except ValueError as ve:
            logger.error(f"Job {job_id}: Validation error in video processing: {str(ve)}")
            return {"error": f"Validation error: {str(ve)}"}, "/v1/video/scripted", 400
        except RuntimeError as re:
            logger.error(f"Job {job_id}: Processing error: {str(re)}")
            return {"error": f"Video processing error: {str(re)}"}, "/v1/video/scripted", 500
        except Exception as e:
            logger.error(f"Job {job_id}: Unexpected error during video processing: {str(e)}", exc_info=True)
            return {"error": f"Unexpected error: {str(e)}"}, "/v1/video/scripted", 500
        
        # If result is a dict with error key, it's an error response from the service
        if isinstance(output_path, dict) and 'error' in output_path:
            return {"error": output_path['error']}, "/v1/video/scripted", 400

        # Check if we got a valid output path
        if not output_path or not isinstance(output_path, str):
            error_msg = "Video processor did not return a valid output path"
            logger.error(f"Job {job_id}: {error_msg}")
            return {"error": error_msg}, "/v1/video/scripted", 500
            
        logger.info(f"Job {job_id}: Video processing completed successfully")
        
        # Verify the output file exists and is valid
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            error_msg = "Final video file is missing or empty"
            logger.error(f"Job {job_id}: {error_msg}")
            return {"error": error_msg}, "/v1/video/scripted", 500

        # Get video duration for reporting to the client
        video_duration = None
        try:
            video_duration = get_media_duration(output_path)
        except Exception as e:
            logger.warning(f"Job {job_id}: Could not determine video duration: {str(e)}")

        # Upload the final video
        cloud_url = None
        try:
            cloud_url = upload_file(output_path)
            logger.info(f"Job {job_id}: Video uploaded to cloud storage: {cloud_url}")
        except Exception as upload_error:
            logger.error(f"Job {job_id}: Failed to upload video: {str(upload_error)}", exc_info=True)
            return {
                "error": f"Video processing succeeded but upload failed: {str(upload_error)}",
                "details": "The video was created successfully but could not be uploaded to cloud storage"
            }, "/v1/video/scripted", 500
        
        # Clean up the output file after upload
        try:
            if output_path and os.path.exists(output_path):
                os.remove(output_path)
                logger.info(f"Job {job_id}: Cleaned up local output file")
        except Exception as cleanup_error:
            # Log but don't fail if cleanup fails
            logger.warning(f"Job {job_id}: Failed to clean up output file: {str(cleanup_error)}")

        # Calculate processing time
        processing_time = time.time() - start_time
        logger.info(f"Job {job_id}: Total processing time: {processing_time:.2f} seconds")

        # Prepare successful response with additional information
        response = {
            "video_url": cloud_url,
            "message": "Video successfully generated"
        }
        
        # Add optional information if available
        if request_id:
            response["id"] = request_id
            
        if video_duration:
            response["duration"] = round(video_duration, 2)
            
        response["processing_time"] = round(processing_time, 2)

        return response, "/v1/video/scripted", 200

    except ValueError as ve:
        # Handle validation errors
        error_msg = str(ve)
        logger.error(f"Job {job_id}: Validation error during video processing - {error_msg}")
        return {"error": f"Validation error: {error_msg}"}, "/v1/video/scripted", 400
        
    except FileNotFoundError as fe:
        # Handle missing file errors
        error_msg = str(fe)
        logger.error(f"Job {job_id}: File not found during video processing - {error_msg}")
        return {"error": f"File not found: {error_msg}"}, "/v1/video/scripted", 400
        
    except RuntimeError as re:
        # Handle runtime errors
        error_msg = str(re)
        logger.error(f"Job {job_id}: Runtime error during video processing - {error_msg}")
        return {"error": f"Processing error: {error_msg}"}, "/v1/video/scripted", 500
        
    except Exception as e:
        # Handle all other errors
        logger.error(f"Job {job_id}: Unexpected error during video processing - {str(e)}", exc_info=True)
        return {"error": f"Unexpected error: {str(e)}"}, "/v1/video/scripted", 500
    finally:
        # Make sure we clean up output file if it exists and something went wrong
        if output_path and os.path.exists(output_path):
            try:
                os.remove(output_path)
                logger.debug(f"Job {job_id}: Cleaned up output file in finally block")
            except Exception:
                pass
