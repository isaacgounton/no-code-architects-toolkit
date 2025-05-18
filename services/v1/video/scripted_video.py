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

import os
import logging
import asyncio
import json
import subprocess
import re
import nltk
import time
from nltk.tokenize import word_tokenize
from nltk.tag import pos_tag
from services.v1.audio.speech import generate_tts
import uuid
from typing import List, Dict, Any, Optional, Union
import aiohttp
from config import LOCAL_STORAGE_PATH, PEXELS_API_KEY, PIXABAY_API_KEY, DEFAULT_PLACEHOLDER_VIDEO
from services.v1.video.caption_video import process_captioning_v1
import tempfile
import whisper
from nltk.corpus import stopwords

# Initialize logger
logger = logging.getLogger(__name__)

# Constants for video resolutions
RESOLUTIONS = {
    "16:9": (1920, 1080),
    "9:16": (1080, 1920),
    "1:1": (1080, 1080)
}

def synthesize_voice_sync(text: str, tts_engine: str, voice: str, target_mp3_path: str) -> str:
    """
    Synchronously synthesize voice to MP3 format at the target_mp3_path
    using the main generate_tts service.
    """
    try:
        # Generate a unique job_id for the call to generate_tts
        tts_job_id = str(uuid.uuid4())

        # Call the main TTS service, requesting MP3 format
        temp_mp3_path, _ = generate_tts(
            tts=tts_engine,
            text=text,
            voice=voice,
            job_id=tts_job_id,
            output_format="mp3"
        )

        # Ensure the target directory for the final MP3 exists
        target_dir = os.path.dirname(target_mp3_path)
        if not os.path.exists(target_dir):
            os.makedirs(target_dir, exist_ok=True)

        # Move the generated MP3 to the specific path
        if os.path.exists(temp_mp3_path):
            os.rename(temp_mp3_path, target_mp3_path)
        else:
            raise FileNotFoundError(f"generate_tts did not produce the expected MP3 file at {temp_mp3_path}")
            
        return target_mp3_path
    except Exception as e:
        logger.error(f"Voice synthesis error in synthesize_voice_sync: {str(e)}")
        raise

async def synthesize_voice(text: str, tts_engine: str, voice: str, target_mp3_path: str) -> str:
    """
    Asynchronously synthesize voice to MP3 format at the target_mp3_path.
    """
    try:
        # Run the synchronous synthesis in an executor
        return await asyncio.get_event_loop().run_in_executor(
            None, synthesize_voice_sync, text, tts_engine, voice, target_mp3_path
        )
    except Exception as e:
        logger.error(f"Asynchronous voice synthesis error: {str(e)}")
        raise

async def fetch_from_pexels(query: str, media_type: str = "video") -> List[Dict[str, Any]]:
    """
    Fetch stock media from Pexels based on query
    """
    headers = {
        "Authorization": PEXELS_API_KEY
    }
    endpoint = f"https://api.pexels.com/videos/search" if media_type == "video" else "https://api.pexels.com/v1/search"
    params = {
        "query": query,
        "per_page": 5,
        "orientation": "landscape" if media_type == "video" else "square"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(endpoint, headers=headers, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("videos" if media_type == "video" else "photos", [])
                else:
                    logger.error(f"Pexels API error: {response.status}")
                    return []
    except Exception as e:
        logger.error(f"Pexels fetch error: {str(e)}")
        return []

async def fetch_from_pixabay(query: str, media_type: str = "video") -> List[Dict[str, Any]]:
    """
    Fetch stock media from Pixabay based on query
    """
    endpoint = "https://pixabay.com/api/videos" if media_type == "video" else "https://pixabay.com/api"
    params = {
        "key": PIXABAY_API_KEY,
        "q": query,
        "per_page": 5
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(endpoint, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("hits", [])
                else:
                    logger.error(f"Pixabay API error: {response.status}")
                    return []
    except Exception as e:
        logger.error(f"Pixabay fetch error: {str(e)}")
        return []

import functools
from typing import Dict, Optional, Tuple
import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

# Global state
used_videos = set()
max_retries = 3
retry_delay = 1  # seconds

def validate_video_file(file_path: str) -> bool:
    """
    Validate video file using FFprobe - checks that file exists, 
    is non-empty, and contains valid video and audio streams
    """
    if not os.path.exists(file_path):
        logger.error(f"Video file does not exist: {file_path}")
        return False
        
    if os.path.getsize(file_path) == 0:
        logger.error(f"Video file is empty: {file_path}")
        return False
    
    try:
        # Check for valid video streams
        command = [
            'ffprobe',
            '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=codec_type,duration',
            '-of', 'json',
            file_path
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        
        # If ffprobe returns an error or empty output, the file is invalid
        if result.stderr.strip():
            logger.error(f"FFprobe error for {file_path}: {result.stderr.strip()}")
            return False
            
        video_data = json.loads(result.stdout)
        
        # Verify we have a video stream
        if 'streams' not in video_data or len(video_data['streams']) == 0:
            logger.error(f"No video streams found in {file_path}")
            return False
        
        # Check stream is actually a video stream
        if video_data['streams'][0].get('codec_type') != 'video':
            logger.error(f"First stream is not a video stream in {file_path}")
            return False
            
        # Optionally check for audio stream as well
        command = [
            'ffprobe',
            '-v', 'error',
            '-select_streams', 'a:0',
            '-show_entries', 'stream=codec_type',
            '-of', 'json',
            file_path
        ]
        audio_result = subprocess.run(command, capture_output=True, text=True)
        
        # Not having audio is not necessarily an error for raw video files
        audio_data = json.loads(audio_result.stdout)
        has_audio = 'streams' in audio_data and len(audio_data['streams']) > 0
        
        if not has_audio:
            logger.warning(f"No audio stream found in {file_path}, but this may be intentional")
            
        # Check if the file can be read from start to finish
        command = [
            'ffmpeg',
            '-v', 'error',
            '-i', file_path,
            '-f', 'null',
            '-'
        ]
        read_result = subprocess.run(command, capture_output=True, text=True)
        
        if read_result.stderr.strip():
            logger.error(f"Failed to read video file {file_path} from start to finish: {read_result.stderr.strip()}")
            return False
        
        return True
    except Exception as e:
        logger.error(f"Video file validation failed for {file_path}: {str(e)}")
        return False

def get_media_duration(file_path: str) -> float:
    """
    Get duration of a media file using FFprobe, with additional validation
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Media file not found: {file_path}")
        
    if os.path.getsize(file_path) == 0:
        raise ValueError(f"Media file is empty: {file_path}")
    
    try:
        # First try with format/duration which is faster
        command = [
            'ffprobe',
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            file_path
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        
        if result.stdout.strip() and not result.stderr.strip():
            try:
                return float(result.stdout.strip())
            except ValueError:
                # If parsing failed, continue to the fallback method
                pass
        
        # Fallback to stream duration if format duration not available
        command = [
            'ffprobe',
            '-v', 'error',
            '-select_streams', 'v:0',  # Select first video stream
            '-show_entries', 'stream=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            file_path
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        
        if not result.stdout.strip() or result.stderr.strip():
            raise ValueError(f"Could not determine media duration: {result.stderr.strip()}")
        
        return float(result.stdout.strip())
    except Exception as e:
        logger.error(f"Error getting media duration for {file_path}: {str(e)}")
        raise

async def with_retries(func, *args, retries=max_retries, delay=retry_delay):
    """Retry a function with exponential backoff"""
    last_error = None
    func_name = getattr(func, '__name__', str(func))
    logger.info(f"Starting retry wrapper for {func_name} with {retries} max retries")
    
    for attempt in range(retries):
        try:
            result = await func(*args)
            if attempt > 0:
                logger.info(f"Successfully completed {func_name} after {attempt + 1} attempts")
            return result
        except Exception as e:
            last_error = e
            if attempt < retries - 1:
                wait_time = delay * (2 ** attempt)
                logger.warning(f"Retry attempt {attempt + 1} for {func_name} after error: {str(e)}. Waiting {wait_time}s...")
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"All {retries} retries failed for {func_name}: {str(e)}")
                raise last_error

async def fetch_stock_media(query: str, media_type: str = "video", custom_url: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Fetch stock media with fallback options, retries, and custom URL support
    """
    global used_videos

    if custom_url:
        # Custom URLs bypass retry mechanism
        return [{
            "video_files" if media_type == "video" else "photos": [{
                "link": custom_url
            }]
        }]
    
    # Try Pexels first with retries
    results = await with_retries(fetch_from_pexels, query, media_type)
    
    # Filter out already used videos and try to find a new one
    if results:
        for result in results:
            video_url = result.get("video_files", [{}])[0].get("link") if media_type == "video" else result.get("photos", [{}])[0].get("link")
            if video_url and video_url not in used_videos:
                used_videos.add(video_url)
                return [result]
    
    # If no new results from Pexels, try Pixabay
    logger.info(f"No new results from Pexels for '{query}', trying Pixabay")
    pixabay_results = await fetch_from_pixabay(query, media_type)
    
    if pixabay_results:
        # Convert Pixabay format to match Pexels format and filter used videos
        for item in pixabay_results:
            video_url = item.get("videos", {}).get("large", {}).get("url") if media_type == "video" else item.get("largeImageURL")
            if video_url and video_url not in used_videos:
                used_videos.add(video_url)
                return [{
                    "video_files" if media_type == "video" else "photos": [{
                        "link": video_url
                    }]
                }]
    
    # Try alternative keywords
    alt_keywords = generate_alternative_keywords(query)
    for alt_query in alt_keywords:
        logger.info(f"Trying alternative query: {alt_query}")
        
        # Try Pexels with alternative keywords
        results = await fetch_from_pexels(alt_query, media_type)
        if results:
            for result in results:
                video_url = result.get("video_files", [{}])[0].get("link") if media_type == "video" else result.get("photos", [{}])[0].get("link")
                if video_url and video_url not in used_videos:
                    used_videos.add(video_url)
                    return [result]
        
        # Try Pixabay with alternative keywords
        pixabay_results = await fetch_from_pixabay(alt_query, media_type)
        if pixabay_results:
            for item in pixabay_results:
                video_url = item.get("videos", {}).get("large", {}).get("url") if media_type == "video" else item.get("largeImageURL")
                if video_url and video_url not in used_videos:
                    used_videos.add(video_url)
                    return [{
                        "video_files" if media_type == "video" else "photos": [{
                            "link": video_url
                        }]
                    }]
    
    # If we still didn't find any new videos, return the first result we found originally
    # even if it was used before
    if results:
        return [results[0]]
    if pixabay_results:
        return [{
            "video_files" if media_type == "video" else "photos": [{
                "link": pixabay_results[0].get("videos", {}).get("large", {}).get("url") if media_type == "video" else pixabay_results[0].get("largeImageURL")
            }]
        }]
    
    return []

def generate_alternative_keywords(query: str) -> List[str]:
    """
    Generate alternative keyword combinations for better media matching
    """
    words = word_tokenize(query.lower())
    tagged = pos_tag(words)
    
    # Extract nouns and verbs as they're most relevant for visual content
    keywords = [word for word, tag in tagged if tag.startswith(('NN', 'VB'))]
    
    # Generate combinations
    alternatives = []
    if len(keywords) > 1:
        # Try pairs of keywords
        for i in range(len(keywords)-1):
            alternatives.append(f"{keywords[i]} {keywords[i+1]}")
    
    # Add individual keywords
    alternatives.extend(keywords)
    
    # Add original query
    if query.lower() not in alternatives:
        alternatives.append(query.lower())
    
    return alternatives

async def download_media(url: str, output_path: str) -> str:
    """
    Download media from URL
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    with open(output_path, 'wb') as f:
                        while True:
                            chunk = await response.content.read(8192)
                            if not chunk:
                                break
                            f.write(chunk)
                    return output_path
                else:
                    raise Exception(f"Failed to download media: {response.status}")
    except Exception as e:
        logger.error(f"Media download error: {str(e)}")
        raise

def extract_scenes(script: str) -> List[str]:
    """
    Split script into scenes based on natural paragraph breaks.
    Each paragraph (separated by double newlines) becomes a scene.
    """
    # Split by double newlines and clean up
    scenes = [scene.strip() for scene in script.split("\n\n") if scene.strip()]
    
    # Filter out any empty scenes
    scenes = [scene for scene in scenes if scene]
    
    if not scenes:
        raise ValueError("Script is empty or contains no valid content")
        
    return scenes

def get_scene_keywords(scene: str) -> List[str]:
    """
    Extract relevant keywords from scene for media search
    """
    # Remove common words and get key nouns/verbs
    common_words = set(['the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for'])
    words = scene.lower().split()
    keywords = [word for word in words if word not in common_words and len(word) > 3]
    return list(set(keywords[:5]))  # Return up to 5 unique keywords

# Remove duplicate get_media_duration function since it was already replaced

def crop_video_to_aspect_ratio(video_path: str, target_ratio: str, output_path: str) -> str:
    """
    Crop video to desired aspect ratio using FFmpeg, with better centering and error handling
    """
    try:
        # Verify the input file exists
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Input video file not found: {video_path}")
            
        # Define target resolutions based on aspect ratio
        if target_ratio not in RESOLUTIONS:
            raise ValueError(f"Unsupported aspect ratio: {target_ratio}. Supported ratios: {', '.join(RESOLUTIONS.keys())}")
            
        target_width, target_height = RESOLUTIONS[target_ratio]
        target_ratio_value = target_width / target_height
        
        # Get video dimensions using ffprobe
        probe_cmd = [
            'ffprobe',
            '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height,r_frame_rate,codec_name',
            '-of', 'json',
            video_path
        ]
        result = subprocess.run(probe_cmd, capture_output=True, text=True)
        
        if result.stderr:
            logger.error(f"FFprobe error: {result.stderr}")
            raise RuntimeError(f"Failed to analyze video dimensions: {result.stderr}")
            
        video_info = json.loads(result.stdout)
        
        if 'streams' not in video_info or not video_info['streams']:
            raise ValueError("No video stream found in the input file")
            
        stream = video_info['streams'][0]
        width = int(stream['width'])
        height = int(stream['height'])
        current_ratio = width / height
        
        # Get original frame rate for quality preservation
        frame_rate = None
        if 'r_frame_rate' in stream:
            try:
                # r_frame_rate is usually in the form '30000/1001' for 29.97 fps
                numerator, denominator = map(int, stream['r_frame_rate'].split('/'))
                if denominator > 0:
                    frame_rate = numerator / denominator
            except (ValueError, ZeroDivisionError):
                logger.warning(f"Could not parse frame rate: {stream.get('r_frame_rate')}")
        
        # Choose encoding preset based on codec and resolution
        preset = 'medium'  # Default preset (balance between speed and quality)
        if width * height > 1920 * 1080:
            preset = 'slow'  # For higher resolutions, use higher quality preset
            
        # Get original codec
        codec = stream.get('codec_name', 'h264')
        
        # Calculate crop dimensions to maintain proper centering
        if current_ratio > target_ratio_value:
            # Video is too wide, crop width
            new_width = int(height * target_ratio_value)
            crop_x = (width - new_width) // 2
            filter_complex = f'crop={new_width}:{height}:{crop_x}:0,scale={target_width}:{target_height}'
        else:
            # Video is too tall, crop height
            new_height = int(width / target_ratio_value)
            crop_y = (height - new_height) // 2
            filter_complex = f'crop={width}:{new_height}:0:{crop_y},scale={target_width}:{target_height}'
        
        # Build FFmpeg command with all options
        cmd = [
            'ffmpeg',
            '-i', video_path,
            '-vf', filter_complex
        ]
        
        # Add frame rate if available
        if frame_rate:
            cmd.extend(['-r', str(frame_rate)])
            
        # Add encoding options
        cmd.extend([
            '-c:v', 'libx264',
            '-preset', preset,
            '-crf', '23',
            '-profile:v', 'high',
            '-pix_fmt', 'yuv420p',
            '-movflags', '+faststart',
            '-c:a', 'aac',
            '-q:a', '2',
            '-y',
            output_path
        ])
        
        # Create output directory if it doesn't exist
        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            
        # Execute FFmpeg command
        process = subprocess.run(cmd, check=True, capture_output=True, text=True)
        
        # Verify the output file was created
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            logger.error("FFmpeg did not produce valid output file")
            raise RuntimeError("Failed to crop video: Output file is empty or does not exist")
            
        logger.info(f"Successfully cropped video to {target_ratio} ratio ({target_width}x{target_height})")
        
        return output_path
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg error in crop_video_to_aspect_ratio: {e.stderr}")
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except:
                pass
        raise
    except Exception as e:
        logger.error(f"Error cropping video: {str(e)}")
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except:
                pass
        raise

def combine_video_audio(video_path: str, audio_path: str, output_path: str, video_duration: float, audio_duration: float) -> str:
    """
    Combine video and audio using FFmpeg, with smoother transitions for looped video
    Improved handling of video looping to avoid abrupt cuts and repetition issues
    """
    try:
        # Ensure output directory exists
        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        
        # Verify input files exist and are valid
        for file_path, file_type in [(video_path, "Video"), (audio_path, "Audio")]:
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"{file_type} file not found: {file_path}")
            if os.path.getsize(file_path) == 0:
                raise ValueError(f"{file_type} file is empty: {file_path}")
        
        # Additional validation for video file
        if not validate_video_file(video_path):
            raise ValueError(f"Input video file is invalid or corrupted: {video_path}")
        
        temp_files = []  # Track all temp files for cleanup
        looped_video = None
        
        # If video is shorter than audio, we need to loop it
        if video_duration < audio_duration:
            try:
                # Calculate number of loops needed with a small buffer
                num_loops = int(audio_duration / video_duration) + 1
                
                if video_duration >= 3.0 and num_loops > 1:
                    # For videos >= 3 seconds, use crossfade transitions for smoother loops
                    
                    # 1. Extract video without audio for processing
                    silent_video = os.path.join(os.path.dirname(output_path), f"silent_video_{uuid.uuid4()}.mp4")
                    temp_files.append(silent_video)
                    
                    subprocess.run([
                        'ffmpeg',
                        '-i', video_path,
                        '-c:v', 'libx264',  # Re-encode to ensure compatibility
                        '-an',  # No audio
                        '-y',
                        silent_video
                    ], check=True, capture_output=True, text=True)
                    
                    # 2. Create a complex filter for crossfades between loops
                    fade_duration = min(0.5, video_duration / 4)  # Fade duration (max 0.5s or 1/4 of video)
                    
                    # Build filter complex with crossfades
                    # Create input stream references
                    input_args = []
                    filter_complex = ""
                    
                    # Generate enough loops to cover audio duration
                    total_duration_needed = audio_duration + fade_duration  # Add extra for safe margin
                    total_loops_needed = int(total_duration_needed / (video_duration - fade_duration)) + 1
                    
                    # Set up inputs and crossfade filter
                    for i in range(total_loops_needed):
                        input_args.extend(['-i', silent_video])
                    
                    # Simplified crossfade filter
                    filter_complex = ""
                    for i in range(total_loops_needed):
                        filter_complex += f"[{i}:v]trim=0:{video_duration},setpts=PTS-STARTPTS[v{i}];"
                    
                    # Chain videos together with crossfade
                    filter_complex += f"[v0]"
                    for i in range(1, total_loops_needed):
                        filter_complex += f"[v{i}]xfade=transition=fade:duration={fade_duration}:offset={i*video_duration-fade_duration},"
                    
                    filter_complex = filter_complex.replace("[xfaded0]", f"[0:v]trim=start=0:end={video_duration},setpts=PTS-STARTPTS[xfaded0];[xfaded0]")
                    filter_complex += f"[xfaded{total_loops_needed-1}]trim=0:{audio_duration+fade_duration}[vout]"
                    
                    # Apply the complex filter
                    looped_video = os.path.join(os.path.dirname(output_path), f"looped_complex_{uuid.uuid4()}.mp4")
                    temp_files.append(looped_video)
                    
                    ffmpeg_cmd = ['ffmpeg']
                    for _ in range(total_loops_needed):
                        ffmpeg_cmd.extend(['-i', silent_video])
                    
                    ffmpeg_cmd.extend([
                        '-filter_complex', filter_complex,
                        '-map', '[vout]',
                        '-c:v', 'libx264',
                        '-preset', 'medium',
                        '-crf', '23',
                        '-y',
                        looped_video
                    ])
                    
                    result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
                    
                    # Check if the command failed
                    if result.returncode != 0:
                        logger.warning(f"Complex crossfade method failed, falling back to simpler method: {result.stderr}")
                        # Fall back to simpler method
                        looped_video = None
                    elif not validate_video_file(looped_video):
                        logger.warning("Complex crossfade produced invalid video, falling back to simpler method")
                        looped_video = None
                        
                # If complex method failed or wasn't used, try simpler concatenation with fade transitions
                if looped_video is None:
                    # Create a loop file with xfade filters
                    loop_file = os.path.join(os.path.dirname(output_path), f"loop_list_{uuid.uuid4()}.txt")
                    temp_files.append(loop_file)
                    
                    with open(loop_file, 'w', encoding='utf-8') as f:
                        for _ in range(num_loops + 1):  # Add extra loop for safety
                            # Properly escape backslashes and single quotes in paths for ffmpeg
                            escaped_path = video_path.replace('\\', '\\\\').replace("'", "'\\''")
                            f.write(f"file '{escaped_path}'\n")
                    
                    # Concatenate the video loops
                    looped_video = os.path.join(os.path.dirname(output_path), f"looped_video_{uuid.uuid4()}.mp4")
                    temp_files.append(looped_video)
                    
                    # Use concat demuxer for better compatibility and stability
                    subprocess.run([
                        'ffmpeg',
                        '-f', 'concat',
                        '-safe', '0',
                        '-i', loop_file,
                        '-c:v', 'libx264',  # Re-encode for stability
                        '-preset', 'medium',
                        '-crf', '23',
                        '-an',  # No audio yet
                        '-y',
                        looped_video
                    ], check=True, capture_output=True, text=True)
                
                # Validate the looped video
                if not validate_video_file(looped_video):
                    raise ValueError(f"Failed to create valid looped video - try using a different source video")
                
                # Then trim and combine with audio
                cmd = [
                    'ffmpeg',
                    '-i', looped_video,
                    '-i', audio_path,
                    '-t', str(audio_duration),
                    '-map', '0:v:0',
                    '-map', '1:a:0',
                    '-c:v', 'libx264',  # Re-encode to ensure compatibility
                    '-preset', 'medium',
                    '-c:a', 'aac',
                    '-b:a', '192k',
                    '-shortest',  # Ensure output duration matches the shortest
                    '-avoid_negative_ts', 'make_zero',  # Avoid timestamp issues
                    '-y',
                    output_path
                ]
                subprocess.run(cmd, check=True, capture_output=True, text=True)
                
            finally:
                # Clean up all temporary files
                for temp_file in temp_files:
                    if temp_file and os.path.exists(temp_file):
                        try:
                            os.remove(temp_file)
                            logger.debug(f"Removed temp file {temp_file}")
                        except Exception as e:
                            logger.warning(f"Failed to remove temp file {temp_file}: {str(e)}")
        else:
            # Video is longer than audio, just trim and combine
            cmd = [
                'ffmpeg',
                '-i', video_path,
                '-i', audio_path,
                '-t', str(audio_duration + 0.1),  # Add small buffer to avoid cutoffs
                '-map', '0:v:0',
                '-map', '1:a:0',
                '-c:v', 'libx264',  # Re-encode for better compatibility
                '-preset', 'medium',
                '-c:a', 'aac',
                '-b:a', '192k',
                '-shortest',  # Ensure output duration matches the shortest input
                '-y',
                output_path
            ]
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        
        # Verify the output file was created and is valid
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise RuntimeError(f"Failed to create valid output file: {output_path}")
        
        if not validate_video_file(output_path):
            raise RuntimeError(f"Output video is invalid or corrupted: {output_path}")
            
        # Double-check the video duration to ensure it matches audio duration
        final_duration = get_media_duration(output_path)
        if abs(final_duration - audio_duration) > 0.5:  # Allow small difference
            logger.warning(f"Video duration ({final_duration}s) differs from audio ({audio_duration}s) by more than 0.5s")
            
        return output_path
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg error in combine_video_audio: {e.stderr}")
        # Clean up output file if it exists but is invalid
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except:
                pass
        raise RuntimeError(f"FFmpeg error: {e.stderr}")
    except Exception as e:
        logger.error(f"Error combining video and audio: {str(e)}")
        # Clean up output file if it exists but is invalid
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except:
                pass
        raise

def concatenate_videos(video_paths: List[str], output_path: str) -> str:
    """
    Concatenate multiple videos using FFmpeg with improved format standardization
    and path escaping for better compatibility and reliability
    """
    # Validate inputs
    if not video_paths:
        raise ValueError("No video paths provided for concatenation")
        
    # Verify all paths exist and are valid
    missing_files = [path for path in video_paths if not os.path.exists(path)]
    if missing_files:
        raise FileNotFoundError(f"Video files not found: {', '.join(missing_files)}")
        
    # Validate each video file
    invalid_files = []
    for path in video_paths:
        if not validate_video_file(path):
            invalid_files.append(path)
    if invalid_files:
        raise ValueError(f"Invalid video files: {', '.join([os.path.basename(p) for p in invalid_files])}")
    
    # Check if videos have compatible formats
    video_info_list = []
    for path in video_paths:
        try:
            # Get video info using ffprobe
            probe_cmd = [
                'ffprobe',
                '-v', 'error',
                '-select_streams', 'v:0',
                '-show_entries', 'stream=width,height,codec_name,r_frame_rate,pix_fmt',
                '-of', 'json',
                path
            ]
            result = subprocess.run(probe_cmd, capture_output=True, text=True)
            
            if result.stderr:
                logger.warning(f"FFprobe warning for {os.path.basename(path)}: {result.stderr}")
                
            video_info = json.loads(result.stdout)
            if 'streams' in video_info and video_info['streams']:
                video_info_list.append(video_info['streams'][0])
            else:
                raise ValueError(f"Could not read video stream from {os.path.basename(path)}")
        except Exception as e:
            logger.error(f"Error checking video file {path}: {str(e)}")
            raise
    
    # Check format compatibility - if different, standardize before concatenating
    need_standardization = False
    standardized_paths = []
    temp_files = []  # Track all temp files for cleanup
    target_width = None
    target_height = None
    target_codec = None
    target_pix_fmt = None
    
    if len(video_info_list) > 1:
        first_video = video_info_list[0]
        target_width = int(first_video.get('width', 1920))
        target_height = int(first_video.get('height', 1080))
        target_codec = first_video.get('codec_name', 'h264')
        target_pix_fmt = first_video.get('pix_fmt', 'yuv420p')
        
        # Check if any video differs in important parameters
        for i, video_info in enumerate(video_info_list[1:], 1):
            current_width = int(video_info.get('width', 0))
            current_height = int(video_info.get('height', 0))
            current_codec = video_info.get('codec_name', '')
            current_pix_fmt = video_info.get('pix_fmt', '')
            
            # Check for significant incompatibilities
            if (current_width != target_width or 
                current_height != target_height or 
                current_codec != target_codec or
                current_pix_fmt != target_pix_fmt):
                logger.warning(f"Scene {i} has incompatible format with first scene - will standardize all videos")
                logger.debug(f"Format differences: W:{current_width}!={target_width}, H:{current_height}!={target_height}, "
                            f"Codec:{current_codec}!={target_codec}, PixFmt:{current_pix_fmt}!={target_pix_fmt}")
                need_standardization = True
                break
    
    # If formats are incompatible, standardize all videos before concatenation
    if need_standardization:
        logger.info(f"Standardizing {len(video_paths)} videos to ensure compatibility")
        try:
            # Create a unique temp directory to avoid conflicts
            temp_dir = os.path.join(os.path.dirname(output_path), f"std_{uuid.uuid4().hex[:8]}")
            os.makedirs(temp_dir, exist_ok=True)
            temp_files.append(temp_dir)  # Track for cleanup
            
            for i, path in enumerate(video_paths):
                std_path = os.path.join(temp_dir, f"std_{i}.mp4")
                standardized_path = standardize_video_format(path, std_path, target_width, target_height, target_codec, target_pix_fmt)
                standardized_paths.append(standardized_path)
                logger.info(f"Standardized video {i+1}/{len(video_paths)}")
                
                # Verify standardized video
                if not validate_video_file(standardized_path):
                    raise ValueError(f"Standardization failed for video {i+1}")
                
            # Use standardized paths for concatenation
            video_paths_to_concat = standardized_paths
        except Exception as e:
            logger.error(f"Error during video standardization: {str(e)}")
            # Clean up any standardized files if an error occurs
            for path in standardized_paths:
                if os.path.exists(path):
                    try:
                        os.remove(path)
                    except:
                        pass
            # Clean up temp directory
            try:
                import shutil
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
            except:
                pass
            raise RuntimeError(f"Video format standardization failed: {str(e)}")
    else:
        # Use original paths if no standardization needed
        video_paths_to_concat = video_paths
    
    concat_file = None
    concat_id = uuid.uuid4().hex[:8]  # Unique ID for temp files
    
    try:
        # Create a temporary file listing all inputs with proper escaping
        concat_file = os.path.join(os.path.dirname(output_path), f"concat_list_{concat_id}.txt")
        temp_files.append(concat_file)
        
        with open(concat_file, 'w', encoding='utf-8') as f:
            for path in video_paths_to_concat:
                # Escape backslashes and single quotes in paths for ffmpeg
                escaped_path = path.replace('\\', '\\\\').replace("'", "'\\''")
                f.write(f"file '{escaped_path}'\n")
        
        # Create output directory if needed
        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        
        # Always use re-encoding for reliable concatenation
        logger.info("Concatenating videos with re-encoding for reliability...")
        # Re-encode during concatenation for better compatibility
        cmd = [
            'ffmpeg',
            '-f', 'concat',
            '-safe', '0',
            '-i', concat_file,
            '-c:v', 'libx264',
            '-preset', 'medium',
            '-crf', '23',
            '-c:a', 'aac',
            '-b:a', '192k',
            '-pix_fmt', 'yuv420p',  # Ensure compatible pixel format
            '-y',
            output_path
        ]
        
        # Execute FFmpeg command
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        
        # Final verification
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            error_msg = "Concatenated video file was not created or is empty"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        
        # Validate the final video file
        if not validate_video_file(output_path):
            error_msg = "Concatenated video is invalid or corrupted"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
            
        logger.info(f"Successfully concatenated {len(video_paths)} videos to {output_path}")
        return output_path
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg error in concatenate_videos: {e.stderr}")
        # Clean up output file if it exists but is invalid
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
                logger.info(f"Removed invalid output file: {output_path}")
            except:
                pass
        raise RuntimeError(f"FFmpeg error during concatenation: {e.stderr}")
    except Exception as e:
        logger.error(f"Error concatenating videos: {str(e)}")
        # Clean up output file if it exists but is invalid
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
                logger.info(f"Removed invalid output file: {output_path}")
            except:
                pass
        raise
    finally:
        # Clean up all temporary files
        for path in temp_files:
            if path and os.path.exists(path):
                try:
                    if os.path.isdir(path):
                        import shutil
                        shutil.rmtree(path)
                    else:
                        os.remove(path)
                    logger.debug(f"Cleaned up temp file/dir: {path}")
                except Exception as e:
                    logger.warning(f"Failed to clean up temp file/dir {path}: {str(e)}")
        
        # Clean up standardized files
        for path in standardized_paths:
            if path and os.path.exists(path) and path not in temp_files:
                try:
                    os.remove(path)
                    logger.debug(f"Cleaned up standardized file: {path}")
                except Exception as e:
                    logger.warning(f"Failed to clean up standardized file {path}: {str(e)}")

def standardize_video_format(input_path: str, output_path: str, target_width: int = None, 
                        target_height: int = None, target_codec: str = None, target_pix_fmt: str = None) -> str:
    """
    Standardize video format to ensure compatibility for concatenation.
    Enhanced to handle different codecs, pixel formats and improve output quality.
    """
    try:
        # Get video info with comprehensive details
        probe_cmd = [
            'ffprobe',
            '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height,codec_name,pix_fmt,r_frame_rate,bit_rate,duration',
            '-of', 'json',
            input_path
        ]
        result = subprocess.run(probe_cmd, capture_output=True, text=True)
        video_info = json.loads(result.stdout)
        
        # Get audio info too
        audio_probe_cmd = [
            'ffprobe',
            '-v', 'error',
            '-select_streams', 'a:0',
            '-show_entries', 'stream=codec_name,sample_rate,channels',
            '-of', 'json',
            input_path
        ]
        audio_result = subprocess.run(audio_probe_cmd, capture_output=True, text=True)
        audio_info = json.loads(audio_result.stdout)
        has_audio = 'streams' in audio_info and len(audio_info['streams']) > 0
        
        # Validate video stream info
        if 'streams' not in video_info or len(video_info['streams']) == 0:
            raise ValueError(f"No video streams found in {input_path}")
        
        stream = video_info['streams'][0]
        width = int(stream.get('width', 0))
        height = int(stream.get('height', 0))
        source_codec = stream.get('codec_name', '')
        source_pix_fmt = stream.get('pix_fmt', '')
        
        # Parse frame rate
        frame_rate = 30  # Default frame rate
        if 'r_frame_rate' in stream:
            try:
                numerator, denominator = map(int, stream['r_frame_rate'].split('/'))
                if denominator > 0:
                    frame_rate = numerator / denominator
            except (ValueError, ZeroDivisionError):
                logger.warning(f"Could not parse frame rate: {stream.get('r_frame_rate')}, using default")

        # Parse bit rate
        bit_rate = None
        if 'bit_rate' in stream:
            try:
                bit_rate = int(stream['bit_rate'])
            except (ValueError, TypeError):
                pass

        # Determine target values if not specified
        if not target_width or not target_height:
            target_width = width
            target_height = height
            
        if not target_codec:
            target_codec = 'h264'  # Most compatible codec
            
        if not target_pix_fmt:
            target_pix_fmt = 'yuv420p'  # Most compatible pixel format
        
        # Build filter if resizing is needed
        filter_complex = []
        
        # Handle aspect ratio changes with proper letterboxing/pillarboxing
        if width != target_width or height != target_height:
            # Calculate target aspect ratio
            target_ratio = target_width / target_height
            current_ratio = width / height
            
            if abs(current_ratio - target_ratio) > 0.01:  # Small threshold to account for rounding errors
                # Different aspect ratios - use scale with padding to maintain aspect ratio
                filter_complex.append(
                    f'scale={target_width}:{target_height}:force_original_aspect_ratio=decrease,'
                    f'pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2:color=black'
                )
            else:
                # Same aspect ratio - simple scaling
                filter_complex.append(f'scale={target_width}:{target_height}')

        # Handle deinterlacing if needed (common issue with some video sources)
        if 'field_order' in stream and stream['field_order'] not in ['progressive', 'unknown']:
            filter_complex.append('yadif=0:-1:0')  # Add deinterlacing filter
        
        # Apply any enhancements needed for problematic videos
        if source_pix_fmt != target_pix_fmt:
            # No need to add a separate filter for pixel format as we'll set it in output options
            logger.debug(f"Converting pixel format from {source_pix_fmt} to {target_pix_fmt}")
            
        # Determine quality settings based on source
        # Higher quality for high-bitrate sources, standard quality for others
        crf_value = "23"  # Default quality - good balance
        preset = "medium"  # Default preset - balanced speed/quality
        
        # For high-quality sources, preserve more quality
        if bit_rate and bit_rate > 5000000:  # > 5 Mbps
            crf_value = "20"  # Better quality
            preset = "slow"  # Better compression

        # Build FFmpeg command with target format parameters
        cmd = ['ffmpeg', '-i', input_path]
        
        # Add filter complex if needed
        if filter_complex:
            cmd.extend(['-filter_complex', ','.join(filter_complex)])
        
        # Add video codec options
        cmd.extend([
            '-c:v', 'libx264',
            '-preset', preset,
            '-crf', crf_value,
            '-profile:v', 'high',
            '-pix_fmt', target_pix_fmt,
            '-movflags', '+faststart'
        ])
        
        # Add frame rate if significantly different
        if frame_rate and (frame_rate < 20 or frame_rate > 60):
            target_fps = min(max(frame_rate, 24), 60)  # Clamp between 24-60 fps
            cmd.extend(['-r', str(int(target_fps))])
            logger.debug(f"Adjusting frame rate from {frame_rate} to {target_fps}")
        
        # Handle audio
        if has_audio:
            audio_stream = audio_info['streams'][0]
            audio_codec = audio_stream.get('codec_name', '')
            
            # Check if audio needs conversion
            if audio_codec not in ['aac', 'mp3']:
                cmd.extend([
                    '-c:a', 'aac',
                    '-b:a', '192k',
                    '-ar', '48000'  # Standard sample rate
                ])
            else:
                # Keep original audio if it's already compatible
                cmd.extend(['-c:a', 'copy'])
        else:
            # No audio - add silent audio track for compatibility
            cmd.extend([
                '-f', 'lavfi',
                '-i', 'anullsrc=channel_layout=stereo:sample_rate=48000',
                '-c:a', 'aac',
                '-shortest'
            ])
        
        # Ensure output directory exists
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
        
        # Add output path with overwrite flag
        cmd.extend(['-y', output_path])
        
        # Execute FFmpeg command
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        
        # Verify result
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise RuntimeError(f"Failed to create standardized video at {output_path}")
            
        # Validate the standardized video
        if not validate_video_file(output_path):
            raise RuntimeError(f"Standardized video is invalid or corrupted: {output_path}")
            
        logger.debug(f"Standardized video: {os.path.basename(input_path)} -> {os.path.basename(output_path)} " 
                     f"({width}x{height} {source_codec}/{source_pix_fmt} -> "
                     f"{target_width}x{target_height} {target_codec}/{target_pix_fmt})")
            
        return output_path
    
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg error standardizing video format: {e.stderr}")
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except:
                pass
        raise RuntimeError(f"FFmpeg error: {e.stderr}")
    except Exception as e:
        logger.error(f"Error standardizing video format: {str(e)}")
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except:
                pass
        raise

def format_ass_time(seconds):
    """Convert float seconds to ASS time format H:MM:SS.cc"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centiseconds = int(round((seconds - int(seconds)) * 100))
    return f"{hours}:{minutes:02}:{secs:02}.{centiseconds:02}"

async def process_scene(
    scene: str,
    tts: str,
    voice: str,
    aspect_ratio: str,
    job_id: str,
    scene_num: int,
    custom_url: Optional[str] = None,
    use_placeholder: bool = True,
    placeholder_url: Optional[str] = None
) -> str:
    """
    Process a single scene: synthesize voice, fetch and process video, combine
    Enhanced with better error handling, validation, and recovery mechanisms
    """
    scene_dir = os.path.join(LOCAL_STORAGE_PATH, job_id, f"scene_{scene_num}")
    os.makedirs(scene_dir, exist_ok=True)
    
    # Track all temporary files for proper cleanup
    temp_files = []
    raw_video_path = None
    cropped_video_path = None
    audio_path = None
    scene_output_path = None
    
    try:
        # Generate voice for scene with appropriate error handling
        audio_path = os.path.join(scene_dir, "voice.mp3")
        temp_files.append(audio_path)
        
        # Sanitize text for TTS - remove problematic characters if needed
        sanitized_scene = scene.replace('\n', ' ').strip()
        if not sanitized_scene:
            sanitized_scene = "Scene content unavailable."
            logger.warning(f"Empty scene text for scene {scene_num}, using placeholder text")
        
        try:
            await synthesize_voice(sanitized_scene, tts, voice, audio_path)
        except Exception as voice_error:
            logger.error(f"Voice synthesis error for scene {scene_num}: {str(voice_error)}")
            raise RuntimeError(f"Failed to synthesize voice for scene {scene_num}: {str(voice_error)}")

        # Verify that the audio file was created and is valid
        if not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
            err_msg = f"TTS failed to create a valid audio file for scene {scene_num}"
            logger.error(err_msg)
            raise FileNotFoundError(err_msg)
        
        try:
            # Get scene duration from audio
            audio_duration = get_media_duration(audio_path)
            logger.info(f"Scene {scene_num} audio duration: {audio_duration} seconds")
            
            # Validate audio duration is reasonable
            if audio_duration < 0.1:
                logger.error(f"Audio duration too short ({audio_duration}s) for scene {scene_num}")
                raise ValueError(f"Audio duration too short for scene {scene_num}")
                
            if audio_duration > 300:  # 5 minutes max per scene
                logger.warning(f"Audio duration very long ({audio_duration}s) for scene {scene_num}, truncating to 5 minutes")
                audio_duration = 300
        except Exception as duration_error:
            logger.error(f"Error getting audio duration for scene {scene_num}: {str(duration_error)}")
            raise RuntimeError(f"Failed to process audio for scene {scene_num}: {str(duration_error)}")
        
        # Try getting video in order: custom URL -> stock media -> placeholder
        video_url = None
        video_source = "unknown"
        video_fetch_errors = []
        
        # 1. Try custom URL first
        if custom_url:
            logger.info(f"Using custom URL for scene {scene_num}: {custom_url}")
            video_url = custom_url
            video_source = "custom"
        else:
            # 2. Try stock media with multiple keyword combinations
            try:
                # Extract more varied keywords for better search results
                keywords = get_scene_keywords(scene)
                alt_keywords = generate_alternative_keywords(scene)
                
                all_keywords = [" ".join(keywords)]
                if alt_keywords and len(alt_keywords) > 0:
                    all_keywords.extend(alt_keywords[:3])  # Try up to 3 alternative keyword sets
                
                # Try each keyword set until we find a usable video
                for idx, kw in enumerate(all_keywords):
                    logger.info(f"Searching stock videos for scene {scene_num} with keywords [{idx+1}/{len(all_keywords)}]: {kw}")
                    
                    try:
                        stock_videos = await fetch_stock_media(kw)
                        
                        if stock_videos and len(stock_videos) > 0 and 'video_files' in stock_videos[0] and len(stock_videos[0]['video_files']) > 0:
                            video_url = stock_videos[0]['video_files'][0]['link']
                            logger.info(f"Found stock video for scene {scene_num} using keywords: {kw}")
                            video_source = "stock"
                            break
                    except Exception as kw_error:
                        logger.warning(f"Error fetching stock media for scene {scene_num} with keywords '{kw}': {str(kw_error)}")
                        video_fetch_errors.append(str(kw_error))
                        continue
            except Exception as e:
                logger.warning(f"Error in keyword processing for stock media search, scene {scene_num}: {str(e)}")
                video_fetch_errors.append(str(e))
            
            # 3. Fall back to placeholder if stock media failed
            if not video_url and use_placeholder:
                if placeholder_url:
                    logger.warning(f"No stock videos found for scene {scene_num}, using provided placeholder URL")
                    video_url = placeholder_url
                    video_source = "custom_placeholder" 
                elif os.path.exists(DEFAULT_PLACEHOLDER_VIDEO):
                    logger.warning(f"No stock videos found for scene {scene_num}, using default placeholder")
                    video_url = DEFAULT_PLACEHOLDER_VIDEO
                    video_source = "default_placeholder"
                else:
                    logger.error(f"Default placeholder video not found at {DEFAULT_PLACEHOLDER_VIDEO}")
            
            # 4. If still no video, raise error with details
            if not video_url:
                error_details = "; ".join(video_fetch_errors) if video_fetch_errors else "No videos available from any source"
                raise RuntimeError(f"No video source available for scene {scene_num}: {error_details}")
        
        # Add unique identifier to avoid any potential file conflicts
        uid = uuid.uuid4().hex[:6]
        raw_video_path = os.path.join(scene_dir, f"raw_video_{uid}.mp4")
        temp_files.append(raw_video_path)
        
        logger.info(f"Downloading/preparing video for scene {scene_num} from {video_source}")
        
        import shutil
        # Process based on whether it's a local file or URL
        if os.path.exists(video_url) and os.path.isabs(video_url):
            # It's a local file (like the default placeholder)
            try:
                shutil.copy2(video_url, raw_video_path)
                logger.debug(f"Copied local video file for scene {scene_num}")
            except Exception as copy_error:
                logger.error(f"Failed to copy local video file: {str(copy_error)}")
                raise RuntimeError(f"Failed to prepare video for scene {scene_num}: {str(copy_error)}")
        else:
            # It's a URL, download it with proper retries
            success = False
            download_attempts = 0
            max_download_attempts = 3
            
            while not success and download_attempts < max_download_attempts:
                download_attempts += 1
                try:
                    await download_media(video_url, raw_video_path)
                    if os.path.exists(raw_video_path) and os.path.getsize(raw_video_path) > 0:
                        success = True
                    else:
                        logger.warning(f"Downloaded video file is empty, attempt {download_attempts}/{max_download_attempts}")
                except Exception as e:
                    logger.warning(f"Download attempt {download_attempts}/{max_download_attempts} failed: {str(e)}")
                    await asyncio.sleep(1)  # Brief delay between attempts
            
            # If all downloads failed, try placeholder
            if not success:
                logger.error(f"All {max_download_attempts} download attempts failed for scene {scene_num}")
                if use_placeholder and os.path.exists(DEFAULT_PLACEHOLDER_VIDEO):
                    logger.warning(f"Falling back to default placeholder after download failures")
                    shutil.copy2(DEFAULT_PLACEHOLDER_VIDEO, raw_video_path)
                    video_source = "default_placeholder_fallback"
                else:
                    raise RuntimeError(f"Failed to download video and no placeholder available for scene {scene_num}")

        # Validate downloaded/copied video with detailed checking
        try:
            if not validate_video_file(raw_video_path):
                logger.error(f"Invalid or corrupted video file after download/copy for scene {scene_num}")
                if use_placeholder and os.path.exists(DEFAULT_PLACEHOLDER_VIDEO) and video_source != "default_placeholder" and video_source != "default_placeholder_fallback":
                    logger.warning(f"Falling back to default placeholder after validation failure")
                    shutil.copy2(DEFAULT_PLACEHOLDER_VIDEO, raw_video_path)
                    if not validate_video_file(raw_video_path):
                        raise ValueError(f"Default placeholder video is also invalid")
                else:
                    raise ValueError(f"Invalid or corrupted video file and no placeholder available")
        except Exception as validation_error:
            logger.error(f"Video validation error for scene {scene_num}: {str(validation_error)}")
            raise RuntimeError(f"Video validation failed for scene {scene_num}: {str(validation_error)}")
        
        # Crop video to aspect ratio
        cropped_video_path = os.path.join(scene_dir, f"cropped_video_{uid}.mp4")
        temp_files.append(cropped_video_path)
        
        try:
            crop_video_to_aspect_ratio(raw_video_path, aspect_ratio, cropped_video_path)
            
            # Validate cropped video
            if not validate_video_file(cropped_video_path):
                raise ValueError(f"Invalid video after cropping for scene {scene_num}")
                
            # Get video duration
            video_duration = get_media_duration(cropped_video_path)
            logger.info(f"Scene {scene_num} video duration after cropping: {video_duration} seconds")
        except Exception as crop_error:
            logger.error(f"Error cropping video for scene {scene_num}: {str(crop_error)}")
            raise RuntimeError(f"Failed to crop video for scene {scene_num}: {str(crop_error)}")
        
        # Combine video and audio
        scene_output_path = os.path.join(scene_dir, f"final_scene_{uid}.mp4")
        
        try:
            combine_video_audio(cropped_video_path, audio_path, scene_output_path, video_duration, audio_duration)
            
            # Final validation
            if not validate_video_file(scene_output_path):
                raise ValueError(f"Final scene video is invalid or corrupted")
            
            final_duration = get_media_duration(scene_output_path)
            logger.info(f"Scene {scene_num} final duration: {final_duration} seconds")
            
            # Verify final duration is close to audio duration
            if abs(final_duration - audio_duration) > 1.0:  # Allow 1 second difference
                logger.warning(f"Scene {scene_num} final duration ({final_duration}s) differs significantly from audio duration ({audio_duration}s)")
        except Exception as combine_error:
            logger.error(f"Error combining video and audio for scene {scene_num}: {str(combine_error)}")
            raise RuntimeError(f"Failed to combine video and audio for scene {scene_num}: {str(combine_error)}")
        
        return scene_output_path
    except Exception as e:
        logger.error(f"Error processing scene {scene_num}: {str(e)}")
        raise RuntimeError(f"Scene {scene_num} processing failed: {str(e)}")
    finally:
        # Cleanup temporary files - keep only the final scene output
        for file_path in temp_files:
            if file_path and file_path != scene_output_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    logger.debug(f"Cleaned up temp file: {os.path.basename(file_path)}")
                except Exception as cleanup_error:
                    logger.warning(f"Failed to remove temporary file {file_path}: {str(cleanup_error)}")

def process_scripted_video_v1(
    script: str,
    tts: str,
    voice: str,
    aspect_ratio: str,
    add_captions: bool,
    caption_settings: dict,
    job_id: str,
    custom_media: Optional[List[Dict[str, str]]] = None,
    use_placeholder: bool = True,
    placeholder_url: Optional[str] = None
) -> str:
    """
    Process a complete scripted video
    Enhanced with better error handling, scene processing coordination,
    and caption integration
    """
    # Set default values for caption settings to ensure consistency
    caption_settings = caption_settings or {}
    
    # Track generated files for cleanup
    temp_files = []
    final_path = None
    processing_start_time = time.time()
    
    try:
        # Reset the used_videos set for each new video processing
        global used_videos
        used_videos = set()
        
        # Create unique job directory
        job_dir = os.path.join(LOCAL_STORAGE_PATH, job_id)
        os.makedirs(job_dir, exist_ok=True)
        
        # Split script into scenes
        try:
            scenes = extract_scenes(script)
            if not scenes:
                raise ValueError("No valid scenes found in script - please provide paragraphs separated by blank lines")
            
            # Log summary of script and scenes
            total_words = len(script.split())
            logger.info(f"Job {job_id}: Processing {len(scenes)} scenes, total words: {total_words}")
            
            # Warn if script seems too large
            if total_words > 2000:
                logger.warning(f"Job {job_id}: Large script detected ({total_words} words), processing may take longer")
        except Exception as script_error:
            logger.error(f"Script parsing error: {str(script_error)}")
            raise ValueError(f"Invalid script format: {str(script_error)}")
        
        # Process scenes in parallel with a semaphore to control concurrency
        async def process_all_scenes():
            # Limit concurrent scene processing to avoid memory issues
            # Adjust concurrency based on scene count - use fewer workers for many scenes
            max_workers = min(3, 8 // max(1, len(scenes) // 3))
            semaphore = asyncio.Semaphore(max_workers)
            logger.info(f"Using {max_workers} concurrent workers for scene processing")
            
            # Create mapping of scene indices to custom URLs if provided
            custom_urls = {}
            if custom_media:
                try:
                    custom_urls = {int(item['scene_index']): item['media_url'] 
                                for item in custom_media if 'scene_index' in item and 'media_url' in item}
                    logger.info(f"Custom URLs provided for scenes: {list(custom_urls.keys())}")
                    
                    # Validate custom URLs are in range
                    out_of_range = [idx for idx in custom_urls.keys() if idx < 0 or idx >= len(scenes)]
                    if out_of_range:
                        logger.warning(f"Custom media scene indices out of range: {out_of_range}, max valid index: {len(scenes)-1}")
                        # Remove invalid indices but continue processing
                        for idx in out_of_range:
                            del custom_urls[idx]
                except Exception as custom_media_error:
                    logger.error(f"Error processing custom media: {str(custom_media_error)}")
                    # Continue with empty custom_urls rather than failing
                    custom_urls = {}

            # Store any scene processing errors to handle them properly
            scene_errors = []
            
            async def process_scene_with_retries(scene, index):
                scene_start_time = time.time()
                # Create a lambda to wrap the process_scene call with its arguments
                async def process_scene_wrapped():
                    return await process_scene(
                        scene=scene,
                        tts=tts,
                        voice=voice,
                        aspect_ratio=aspect_ratio,
                        job_id=job_id,
                        scene_num=index,
                        custom_url=custom_urls.get(index),
                        use_placeholder=use_placeholder,
                        placeholder_url=placeholder_url
                    )
                
                # Use semaphore to limit concurrent processing and proper error handling
                try:
                    async with semaphore:
                        # Implement more robust retry handling
                        max_attempts = 3
                        last_error = None
                        
                        for attempt in range(max_attempts):
                            try:
                                result = await process_scene_wrapped()
                                scene_duration = time.time() - scene_start_time
                                logger.info(f"Scene {index} completed in {scene_duration:.2f}s on attempt {attempt+1}")
                                return result
                            except Exception as e:
                                last_error = e
                                logger.warning(f"Scene {index} failed on attempt {attempt+1}: {str(e)}")
                                if attempt < max_attempts - 1:
                                    # Progressive backoff delay between attempts
                                    delay = (2 ** attempt) * 1.5
                                    logger.info(f"Retrying scene {index} in {delay:.1f}s...")
                                    await asyncio.sleep(delay)
                        
                        # If we get here, all attempts failed
                        scene_errors.append((index, str(last_error)))
                        logger.error(f"All {max_attempts} attempts failed for scene {index}: {str(last_error)}")
                        return None
                except Exception as e:
                    # This catches any errors in the retry mechanism itself
                    scene_errors.append((index, f"Retry mechanism failed: {str(e)}"))
                    logger.error(f"Critical error in retry mechanism for scene {index}: {str(e)}")
                    return None

            # Process all scenes concurrently
            tasks = [process_scene_with_retries(scene, i) for i, scene in enumerate(scenes)]
            scene_paths = await asyncio.gather(*tasks)
            
            # Check for any failed scenes
            if scene_errors:
                # Sort errors by scene number for better readability
                sorted_errors = sorted(scene_errors, key=lambda x: x[0])
                error_msg = "; ".join([f"Scene {idx}: {err}" for idx, err in sorted_errors])
                
                # Log all errors together for easier debugging
                logger.error(f"Failed scenes [{len(sorted_errors)}/{len(scenes)}]: {error_msg}")
                
                # If more than half of the scenes failed, raise an error
                if len(scene_errors) > len(scenes) / 2:
                    raise RuntimeError(f"Too many scene processing failures ({len(scene_errors)}/{len(scenes)})")
                
                # Otherwise, filter out None values from scene_paths
                scene_paths = [path for path in scene_paths if path is not None]
                logger.warning(f"Continuing with {len(scene_paths)} successfully processed scenes out of {len(scenes)}")
            
            # Ensure we have at least one valid scene
            if not scene_paths:
                raise RuntimeError("All scenes failed to process")
                
            return scene_paths

        # Run the parallel processing
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            scene_paths = loop.run_until_complete(process_all_scenes())
        except Exception as scene_error:
            logger.error(f"Scene processing error: {str(scene_error)}")
            raise RuntimeError(f"Failed to process scenes: {str(scene_error)}")
        finally:
            # Always clean up the loop to prevent event loop leaks
            try:
                loop.close()
            except Exception as loop_error:
                logger.warning(f"Error closing event loop: {str(loop_error)}")
        
        if not scene_paths or len(scene_paths) == 0:
            raise RuntimeError("No valid scenes were processed")
            
        logger.info(f"Successfully processed {len(scene_paths)} scenes, now combining...")
        
        # Combine all scenes
        final_path = os.path.join(job_dir, f"final_video_{uuid.uuid4().hex[:8]}.mp4")
        
        try:
            # Track scene paths for cleanup
            temp_files.extend(scene_paths)
            
            # Concatenate the video scenes
            concatenate_videos(scene_paths, final_path)
            
            # Verify combined video
            if not validate_video_file(final_path):
                raise RuntimeError("Final video file is invalid or corrupted after concatenation")
                
            # Get final duration for reporting
            combined_duration = get_media_duration(final_path)
            logger.info(f"Combined video duration: {combined_duration:.2f} seconds")
        except Exception as concat_error:
            logger.error(f"Error concatenating scenes: {str(concat_error)}")
            raise RuntimeError(f"Failed to combine video scenes: {str(concat_error)}")
        
        # Add captions if requested
        if add_captions:
            logger.info(f"Adding captions to final video")
            # Store the original path for fallback
            original_path = final_path
            captioned_path = None
            
            try:
                # Prepare SRT content
                srt_content = None
                srt_file = os.path.join(job_dir, f"captions_{uuid.uuid4().hex[:8]}.srt")
                temp_files.append(srt_file)
                
                # First try using Whisper for more accurate transcription
                try:
                    # Transcribe final video
                    logger.info("Transcribing video with Whisper...")
                    model = whisper.load_model("base")
                    transcription = model.transcribe(final_path)
                    
                    # Create SRT file content
                    if 'segments' in transcription and transcription['segments']:
                        srt_lines = []
                        for i, segment in enumerate(transcription['segments'], 1):
                            # Format timestamps as SRT format (HH:MM:SS,mmm)
                            start_seconds = segment['start']
                            end_seconds = segment['end']
                            
                            # Ensure minimum duration for each caption (improves readability)
                            if end_seconds - start_seconds < 0.8:
                                end_seconds = min(start_seconds + 0.8, combined_duration)
                            
                            # Format times correctly with padding
                            start_time = format_srt_time(start_seconds)
                            end_time = format_srt_time(end_seconds)
                            
                            # Clean up text
                            text = segment['text'].strip()
                            
                            # Skip empty segments
                            if not text:
                                continue
                                
                            # Format SRT entry
                            srt_lines.extend([
                                str(i),
                                f"{start_time} --> {end_time}",
                                text,
                                ""  # Empty line between entries
                            ])
                        
                        srt_content = "\n".join(srt_lines)
                except Exception as whisper_error:
                    logger.error(f"Whisper transcription error: {str(whisper_error)}")
                    logger.warning("Falling back to original script text for captions")
                    
                    # Fallback: Use the original script text to generate captions
                    srt_content = generate_srt_from_script(script, combined_duration)
                
                # Apply captions using existing caption service
                if srt_content:
                    # Save SRT to file
                    with open(srt_file, "w", encoding="utf-8") as f:
                        f.write(srt_content)
                    
                    # Prepare default caption settings if none provided
                    if not caption_settings:
                        caption_settings = {
                            "line_color": "#ffffff",
                            "word_color": "#ffffff", 
                            "outline_color": "#000000",
                            "all_caps": False,
                            "max_words_per_line": 7,
                            "position": "bottom_center",
                            "alignment": "center",
                            "font_family": "Roboto-Regular.ttf",
                            "font_size": 36,
                            "bold": True
                        }
                    
                    captioned_path = os.path.join(job_dir, f"captioned_final_{uuid.uuid4().hex[:8]}.mp4")
                    
                    # Call captioning service with our SRT content
                    try:
                        process_captioning_result = process_captioning_v1(
                            final_path,          # video_url (local path)
                            srt_content,         # captions (SRT content string)
                            caption_settings,    # settings
                            [],                  # replace (empty list as not supported here)
                            job_id               # job_id
                        )
                        
                        if process_captioning_result and os.path.exists(process_captioning_result):
                            captioned_path = process_captioning_result
                            
                            # Verify captioned video
                            if validate_video_file(captioned_path):
                                logger.info(f"Captioning successful, new video at {captioned_path}")
                                temp_files.append(final_path)  # Add original to temp files for cleanup
                                final_path = captioned_path
                            else:
                                logger.error(f"Captioned video is invalid, falling back to uncaptioned version")
                                # Keep using original path
                                captioned_path = None
                        else:
                            logger.error("Captioning service did not return a valid file path")
                    except Exception as caption_error:
                        logger.error(f"Caption service error: {str(caption_error)}")
                else:
                    logger.warning("No speech content available for captioning")
                    
            except Exception as caption_process_error:
                logger.error(f"Error during captioning process: {str(caption_process_error)}", exc_info=True)
                logger.warning("Continuing with uncaptioned video due to captioning error")
                
                # If we created a captioned file but it's invalid, clean it up
                if captioned_path and captioned_path != final_path and os.path.exists(captioned_path):
                    try:
                        os.remove(captioned_path)
                    except Exception as cleanup_error:
                        logger.warning(f"Failed to clean up invalid captioned file: {str(cleanup_error)}")
        
        # Final verification of output video
        if not os.path.exists(final_path) or os.path.getsize(final_path) == 0:
            raise RuntimeError("Final video file is missing or empty")
            
        if not validate_video_file(final_path):
            raise RuntimeError("Final video file is invalid or corrupted")
            
        processing_time = time.time() - processing_start_time
        logger.info(f"Video processing completed successfully in {processing_time:.2f}s, "
                   f"final duration: {get_media_duration(final_path):.2f} seconds")
        
        return final_path
        
    except Exception as e:
        logger.error(f"Error processing scripted video: {str(e)}")
        # If we've created a final video but encountered an error later, clean it up
        if final_path and os.path.exists(final_path):
            try:
                os.remove(final_path)
                logger.debug("Removed invalid final video file")
            except Exception as cleanup_error:
                logger.warning(f"Failed to clean up final video after error: {str(cleanup_error)}")
        raise
    finally:
        # Clean up all temporary files except the final output
        for file_path in temp_files:
            if file_path and file_path != final_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    logger.debug(f"Cleaned up temporary file: {os.path.basename(file_path)}")
                except Exception as e:
                    logger.warning(f"Failed to clean up file {file_path}: {str(e)}")
        
        # Log final outcome
        if final_path and os.path.exists(final_path) and os.path.getsize(final_path) > 0:
            logger.info(f"Job {job_id} completed successfully, output at: {final_path}")
        else:
            logger.error(f"Job {job_id} failed to produce valid output video")


# Helper function for SRT time formatting
def format_srt_time(seconds: float) -> str:
    """Format time value in SRT format: HH:MM:SS,mmm"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{ms:03}"


# Helper function to generate SRT from script when transcription fails
def generate_srt_from_script(script: str, total_duration: float) -> str:
    """Generate basic SRT file from script text when transcription fails"""
    scenes = extract_scenes(script)
    
    # Skip if no valid scenes
    if not scenes:
        return ""
        
    # Calculate approximate duration per scene
    scene_duration = total_duration / len(scenes)
    
    srt_lines = []
    for i, scene_text in enumerate(scenes, 1):
        # Calculate timing - distribute scenes evenly
        start_time = format_srt_time((i - 1) * scene_duration)
        end_time = format_srt_time(min(i * scene_duration, total_duration))
        
        # Clean up text
        text = scene_text.replace("\n", " ").strip()
        
        # Format SRT entry
        srt_lines.extend([
            str(i),
            f"{start_time} --> {end_time}",
            text,
            ""  # Empty line between entries
        ])
    
    return "\n".join(srt_lines)
