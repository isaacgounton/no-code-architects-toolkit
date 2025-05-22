from flask import Blueprint
from app_utils import *
import logging
from youtube_transcript_api import YouTubeTranscriptApi
from urllib.parse import parse_qs, urlparse
from services.authentication import authenticate
from youtube_transcript_api.formatters import JSONFormatter

v1_youtube_transcript_bp = Blueprint('v1_youtube_transcript', __name__)
logger = logging.getLogger(__name__)

def extract_video_id(url):
    """Extract video ID from various forms of YouTube URLs."""
    if not url:
        return None
        
    parsed_url = urlparse(url)
    
    if parsed_url.hostname in ('www.youtube.com', 'youtube.com'):
        if parsed_url.path == '/watch':
            return parse_qs(parsed_url.query).get('v', [None])[0]
        elif parsed_url.path.startswith('/embed/'):
            return parsed_url.path.split('/')[2]
        elif parsed_url.path.startswith('/v/'):
            return parsed_url.path.split('/')[2]
    elif parsed_url.hostname == 'youtu.be':
        return parsed_url.path[1:]
    
    return None

@v1_youtube_transcript_bp.route('/v1/youtube/transcript', methods=['POST'])
@authenticate
@validate_payload({
    "type": "object",
    "properties": {
        "video_url": {"type": "string", "format": "uri"},
        "languages": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of language codes in order of preference (e.g. ['en', 'es'])"
        },
        "preserve_formatting": {
            "type": "boolean",
            "description": "Whether to preserve HTML formatting (e.g. <i>, <b>)"
        },
        "translate_to": {
            "type": "string",
            "description": "Language code to translate transcript to"
        },
        "cookies_path": {
            "type": "string",
            "description": "Path to cookies file for age-restricted videos"
        }
    },
    "required": ["video_url"],
    "additionalProperties": False
})
def get_transcript(data):
    """Get transcript for a YouTube video with optional translation."""
    try:
        video_url = data['video_url']
        video_id = extract_video_id(video_url)
        
        if not video_id:
            return {"error": "Invalid YouTube URL"}, "/v1/youtube/transcript", 400

        languages = data.get('languages', ['en'])
        preserve_formatting = data.get('preserve_formatting', False)
        translate_to = data.get('translate_to')
        cookies_path = data.get('cookies_path')

        # Initialize API with optional cookies for age-restricted videos
        ytt_api = YouTubeTranscriptApi(cookie_path=cookies_path if cookies_path else None)
        
        try:
            # Get list of available transcripts first
            transcript_list = ytt_api.list(video_id)
            
            # Try to get transcript in requested languages
            transcript = transcript_list.find_transcript(languages)

            # If translation is requested
            if translate_to:
                if transcript.is_translatable:
                    transcript = transcript.translate(translate_to)
                else:
                    return {
                        "error": "Selected transcript cannot be translated"
                    }, "/v1/youtube/transcript", 400

            # Fetch the transcript data
            fetched_transcript = transcript.fetch(preserve_formatting=preserve_formatting)

            # Format response
            response = {
                "video_id": fetched_transcript.video_id,
                "language": {
                    "name": fetched_transcript.language,
                    "code": fetched_transcript.language_code,
                },
                "metadata": {
                    "is_generated": fetched_transcript.is_generated,
                    "translation_languages": transcript.translation_languages if hasattr(transcript, 'translation_languages') else [],
                    "preserve_formatting": preserve_formatting,
                },
                "snippets": [
                    {
                        "text": snippet.text,
                        "start": snippet.start,
                        "duration": snippet.duration
                    } for snippet in fetched_transcript
                ]
            }

            if translate_to:
                response["translated_to"] = translate_to

            return response, "/v1/youtube/transcript", 200

        except Exception as e:
            error_message = str(e)
            if "Transcript is unavailable" in error_message:
                return {
                    "error": "No transcript available for this video"
                }, "/v1/youtube/transcript", 404
            else:
                raise e

    except Exception as e:
        logger.error(f"Error getting transcript: {str(e)}")
        return {"error": str(e)}, "/v1/youtube/transcript", 500
