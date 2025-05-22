from flask import Blueprint
from app_utils import *
import logging
import os
import yt_dlp
import tempfile
from werkzeug.utils import secure_filename
import uuid
from services.cloud_storage import upload_file
from services.authentication import authenticate
from services.file_management import download_file
from urllib.parse import quote, urlparse, parse_qs
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import JSONFormatter

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

v1_media_download_bp = Blueprint('v1_media_download', __name__)
logger = logging.getLogger(__name__)

@v1_media_download_bp.route('/v1/BETA/media/download', methods=['POST'])
@authenticate
@validate_payload({
    "type": "object",
    "properties": {
        "media_url": {"type": "string", "format": "uri"},
        "webhook_url": {"type": "string", "format": "uri"},
        "id": {"type": "string"},
        "cookies_path": {
            "type": "string",
            "description": "Path to cookies file for age-restricted videos"
        },
        "transcript": {
            "type": "object",
            "properties": {
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
                }
            }
        },
        "cookies_path": {
            "type": "string",
            "description": "Path to cookies file for age-restricted videos"
        },
        "format": {
            "type": "object",
            "properties": {
                "quality": {"type": "string"},
                "format_id": {"type": "string"},
                "resolution": {"type": "string"},
                "video_codec": {"type": "string"},
                "audio_codec": {"type": "string"}
            }
        },
        "audio": {
            "type": "object",
            "properties": {
                "extract": {"type": "boolean"},
                "format": {"type": "string"},
                "quality": {"type": "string"}
            }
        },
        "thumbnails": {
            "type": "object",
            "properties": {
                "download": {"type": "boolean"},
                "download_all": {"type": "boolean"},
                "formats": {"type": "array", "items": {"type": "string"}},
                "convert": {"type": "boolean"},
                "embed_in_audio": {"type": "boolean"}
            }
        },
        "subtitles": {
            "type": "object",
            "properties": {
                "download": {"type": "boolean"},
                "languages": {"type": "array", "items": {"type": "string"}},
                "formats": {"type": "array", "items": {"type": "string"}}
            }
        },
        "download": {
            "type": "object",
            "properties": {
                "max_filesize": {"type": "integer"},
                "rate_limit": {"type": "string"},
                "retries": {"type": "integer"}
            }
        }
    },
    "required": ["media_url"],
    "additionalProperties": False
})
@queue_task_wrapper(bypass_queue=False)
def download_media(job_id, data):
    media_url = data['media_url']
    video_id = extract_video_id(media_url)
    
    format_options = data.get('format', {})
    audio_options = data.get('audio', {})
    thumbnail_options = data.get('thumbnails', {})
    subtitle_options = data.get('subtitles', {})
    download_options = data.get('download', {})
    transcript_options = data.get('transcript', {})

    is_youtube = video_id is not None
    logger.info(f"Job {job_id}: Received download request for {'YouTube video' if is_youtube else 'media'} {media_url}")

    # Handle transcript request for YouTube videos
    if is_youtube and transcript_options:
        try:
            languages = transcript_options.get('languages', ['en'])
            preserve_formatting = transcript_options.get('preserve_formatting', False)
            translate_to = transcript_options.get('translate_to')
            cookies_path = data.get('cookies_path')

            # For transcripts, only use cookies if the video is age-restricted
            ytt_api = YouTubeTranscriptApi()  # Start without cookies
            try:
                transcript_list = ytt_api.list(video_id)
            except Exception as e:
                if "too many requests" in str(e).lower() or "sign in to confirm your age" in str(e).lower():
                    # Only use cookies if we hit an age restriction
                    if cookies_path:
                        ytt_api = YouTubeTranscriptApi(cookie_path=cookies_path)
                        transcript_list = ytt_api.list(video_id)
                    else:
                        raise
                else:
                    raise
            
            # Find transcript in requested languages
            transcript = transcript_list.find_transcript(languages)

            # Handle translation if requested
            if translate_to:
                if transcript.is_translatable:
                    transcript = transcript.translate(translate_to)
                else:
                    return {
                        "error": "Selected transcript cannot be translated"
                    }, "/v1/media/download", 400

            # Fetch transcript data
            fetched_transcript = transcript.fetch(preserve_formatting=preserve_formatting)

            # Add transcript data to response
            transcript_data = {
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
                transcript_data["translated_to"] = translate_to

        except Exception as e:
            error_response, status_code = handle_youtube_error(str(e))
            return error_response, "/v1/media/download", status_code

    try:
        # Create a temporary directory for downloads
        with tempfile.TemporaryDirectory() as temp_dir:
            # Configure base yt-dlp options
            ydl_opts = {
                'format': 'best',  # Download best quality
                'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s'),
                'quiet': True,
                'no_warnings': True,
            }

            # For YouTube videos, try without cookies first
            if is_youtube:
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        ydl.extract_info(media_url, download=False)  # Test extraction without downloading
                except Exception as e:
                    error_str = str(e)
                    if any(msg in error_str.lower() for msg in [
                        "sign in to confirm your age",
                        "sign in to continue",
                        "sign in to confirm you're not a bot",
                        "private video"
                    ]):
                        # Only use cookies if we hit an age restriction or similar
                        cookies_path = data.get('cookies_path')
                        if cookies_path:
                            logger.info(f"Job {job_id}: Using cookies from {cookies_path}")
                            ydl_opts['cookiefile'] = cookies_path
                        else:
                            raise
                    else:
                        raise
            # For non-YouTube videos, use cookies if provided
            elif data.get('cookies_path'):
                ydl_opts['cookiefile'] = data.get('cookies_path')

            # Add format options if specified
            if format_options:
                format_str = []
                if format_options.get('quality'):
                    format_str.append(format_options['quality'])
                if format_options.get('format_id'):
                    format_str.append(format_options['format_id'])
                if format_options.get('resolution'):
                    format_str.append(format_options['resolution'])
                if format_options.get('video_codec'):
                    format_str.append(format_options['video_codec'])
                if format_options.get('audio_codec'):
                    format_str.append(format_options['audio_codec'])
                if format_str:
                    ydl_opts['format'] = '+'.join(format_str)

            # Add audio options if specified
            if audio_options:
                if audio_options.get('extract'):
                    ydl_opts['extract_audio'] = True
                    if audio_options.get('format'):
                        ydl_opts['audio_format'] = audio_options['format']
                    if audio_options.get('quality'):
                        ydl_opts['audio_quality'] = audio_options['quality']

            # Add thumbnail options if specified
            if thumbnail_options:
                ydl_opts['writesubtitles'] = thumbnail_options.get('download', False)
                ydl_opts['writeallsubtitles'] = thumbnail_options.get('download_all', False)
                if thumbnail_options.get('formats'):
                    ydl_opts['subtitleslangs'] = thumbnail_options['formats']
                ydl_opts['convert_thumbnails'] = thumbnail_options.get('convert', False)
                ydl_opts['embed_thumbnail_in_audio'] = thumbnail_options.get('embed_in_audio', False)

            # Add subtitle options if specified
            if subtitle_options:
                ydl_opts['writesubtitles'] = subtitle_options.get('download', False)
                if subtitle_options.get('languages'):
                    ydl_opts['subtitleslangs'] = subtitle_options['languages']
                if subtitle_options.get('formats'):
                    ydl_opts['subtitlesformat'] = subtitle_options['formats']

            # Add download options if specified
            if download_options:
                if download_options.get('max_filesize'):
                    ydl_opts['max_filesize'] = download_options['max_filesize']
                if download_options.get('rate_limit'):
                    ydl_opts['limit_rate'] = download_options['rate_limit']
                if download_options.get('retries'):
                    ydl_opts['retries'] = download_options['retries']

            # Download the media
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(media_url, download=True)
                filename = ydl.prepare_filename(info)
                
                # Upload to cloud storage
                cloud_url = upload_file(filename)
                
                # Clean up the temporary file
                os.remove(filename)

                # Prepare response
                response = {
                    "media": {
                        "media_url": cloud_url,
                        "video_id": video_id if is_youtube else None,
                        "title": info.get('title'),
                        "format_id": info.get('format_id'),
                        "ext": info.get('ext'),
                        "resolution": info.get('resolution'),
                        "filesize": info.get('filesize'),
                        "width": info.get('width'),
                        "height": info.get('height'),
                        "fps": info.get('fps'),
                        "video_codec": info.get('vcodec'),
                        "audio_codec": info.get('acodec'),
                        "upload_date": info.get('upload_date'),
                        "duration": info.get('duration'),
                        "view_count": info.get('view_count'),
                        "uploader": info.get('uploader'),
                        "uploader_id": info.get('uploader_id'),
                        "description": info.get('description')
                    }
                }

                # Add thumbnails if available and requested
                if info.get('thumbnails') and thumbnail_options.get('download', False):
                    response["thumbnails"] = []
                    for thumbnail in info['thumbnails']:
                        if thumbnail.get('url'):
                            try:
                                # Download the thumbnail first
                                thumbnail_path = download_file(thumbnail['url'], temp_dir)
                                # Upload to cloud storage
                                thumbnail_url = upload_file(thumbnail_path)
                                # Clean up the temporary thumbnail file
                                os.remove(thumbnail_path)
                                
                                response["thumbnails"].append({
                                    "id": thumbnail.get('id', 'default'),
                                    "image_url": thumbnail_url,
                                    "width": thumbnail.get('width'),
                                    "height": thumbnail.get('height'),
                                    "original_format": thumbnail.get('ext'),
                                    "converted": thumbnail.get('converted', False)
                                })
                            except Exception as e:
                                logger.error(f"Error processing thumbnail: {str(e)}")
                                continue

                # Add transcript data if it was requested and available
                if is_youtube and transcript_options and 'transcript_data' in locals():
                    response["transcript"] = transcript_data
                
                return response, "/v1/media/download", 200

    except Exception as e:
        error_str = str(e)
        logger.error(f"Job {job_id}: Error during download process - {error_str}")
        
        # Handle common YouTube errors with better messages
        if "Sign in to confirm your age" in error_str or "Sign in to continue" in error_str:
            return {
                "error": "Age-restricted or private video requires authentication",
                "solution": "Please provide a cookies_path parameter with valid YouTube cookies. You can export cookies from your browser using browser extensions or yt-dlp's --cookies-from-browser option. See https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp for detailed instructions."
            }, "/v1/media/download", 401
        elif "Sign in to confirm you're not a bot" in error_str:
            return {
                "error": "YouTube is requesting verification",
                "solution": "Please provide a cookies_path parameter with valid YouTube cookies. Export them from your browser using yt-dlp's --cookies-from-browser option or a browser extension. See https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp"
            }, "/v1/media/download", 401
        elif "Video unavailable" in error_str or "This video is not available" in error_str:
            return {
                "error": "Video is not available",
                "details": error_str
            }, "/v1/media/download", 404
        elif "Private video" in error_str:
            return {
                "error": "This is a private video",
                "solution": "If you have access to this video, provide a cookies_path parameter with valid YouTube cookies."
            }, "/v1/media/download", 403
        else:
            return {
                "error": error_str,
                "tip": "If this is a YouTube video requiring authentication, try providing a cookies_path parameter."
            }, "/v1/media/download", 500
