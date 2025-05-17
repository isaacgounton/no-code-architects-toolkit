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
from moviepy.editor import VideoFileClip, AudioFileClip, concatenate_videoclips
import re
import nltk
from nltk.tokenize import word_tokenize
from nltk.tag import pos_tag
from services.v1.audio.speech import generate_tts # Changed import
import uuid # Added import
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
        # generate_tts returns (audio_file_path, subtitle_file_path)
        # We expect audio_file_path to be like /tmp/{tts_job_id}.mp3
        temp_mp3_path, _ = generate_tts(
            tts=tts_engine,
            text=text,
            voice=voice,
            job_id=tts_job_id,
            output_format="mp3" 
            # rate, volume, pitch can be added if needed by scripted_video
        )

        # Ensure the target directory for the final MP3 exists
        target_dir = os.path.dirname(target_mp3_path)
        if not os.path.exists(target_dir):
            os.makedirs(target_dir, exist_ok=True)

        # Move the generated MP3 to the specific path required by the video script
        if os.path.exists(temp_mp3_path):
            os.rename(temp_mp3_path, target_mp3_path)
        else:
            # This case should ideally be handled by generate_tts raising an error
            raise FileNotFoundError(f"generate_tts did not produce the expected MP3 file at {temp_mp3_path}")
            
        return target_mp3_path
    except Exception as e:
        logger.error(f"Voice synthesis error in synthesize_voice_sync: {str(e)}")
        # Log specific details if it's an ffmpeg error from generate_tts
        if isinstance(e, ffmpeg.Error) and e.stderr:
            logger.error(f"FFmpeg stderr: {e.stderr.decode('utf8', errors='ignore')}")
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
        if isinstance(e, ffmpeg.Error) and e.stderr: # Log ffmpeg error details
            logger.error(f"FFmpeg stderr (async): {e.stderr.decode('utf8', errors='ignore')}")
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
video_clip_cache: Dict[str, Tuple[VideoFileClip, int]] = {}  # path -> (clip, ref_count)
max_retries = 3
retry_delay = 1  # seconds

def get_cached_clip(path: str) -> Optional[VideoFileClip]:
    """Get a cached video clip if available"""
    if path in video_clip_cache:
        clip, ref_count = video_clip_cache[path]
        video_clip_cache[path] = (clip, ref_count + 1)
        return clip
    return None

def cache_clip(path: str, clip: VideoFileClip):
    """Cache a video clip"""
    video_clip_cache[path] = (clip, 1)

def release_clip(path: str):
    """Release a cached clip when no longer needed"""
    if path in video_clip_cache:
        clip, ref_count = video_clip_cache[path]
        if ref_count <= 1:
            clip.close()
            del video_clip_cache[path]
        else:
            video_clip_cache[path] = (clip, ref_count - 1)

def validate_video_file(file_path: str) -> bool:
    """Validate video file can be opened and has valid duration"""
    try:
        clip = VideoFileClip(file_path)
        is_valid = hasattr(clip, 'duration') and clip.duration is not None and clip.duration > 0
        clip.close()
        return is_valid
    except Exception as e:
        logger.error(f"Video file validation failed for {file_path}: {str(e)}")
        return False

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

def get_media_duration(file_path: str) -> float:
    """
    Get duration of a media file using MoviePy
    """
    try:
        if file_path.lower().endswith('.mp3'):
            clip = AudioFileClip(file_path)
        else:
            clip = VideoFileClip(file_path)
        duration = clip.duration
        clip.close()
        return duration
    except Exception as e:
        logger.error(f"Error getting media duration: {str(e)}")
        raise

def crop_video_to_aspect_ratio(video_path: str, target_ratio: str, output_path: str) -> str:
    """
    Crop video to desired aspect ratio using MoviePy
    """
    target_width, target_height = RESOLUTIONS[target_ratio]
    target_ratio_value = target_width / target_height
    
    try:
        # Load video clip
        clip = VideoFileClip(video_path)
        
        # Calculate crop dimensions
        current_ratio = clip.w / clip.h
        
        if current_ratio > target_ratio_value:
            # Video is too wide, crop width
            new_width = int(clip.h * target_ratio_value)
            crop_x = (clip.w - new_width) // 2
            cropped = clip.crop(x1=crop_x, width=new_width)
        else:
            # Video is too tall, crop height
            new_height = int(clip.w / target_ratio_value)
            crop_y = (clip.h - new_height) // 2
            cropped = clip.crop(y1=crop_y, height=new_height)
        
        # Resize to target resolution
        final = cropped.resize(width=target_width, height=target_height)
        
        # Write output
        final.write_videofile(output_path, codec='libx264', audio=True)
        
        # Close clips to release resources
        clip.close()
        cropped.close()
        final.close()
        
        return output_path
    except Exception as e:
        logger.error(f"Error cropping video: {str(e)}")
        raise

def combine_video_audio(video_path: str, audio_path: str, output_path: str, video_duration: float, audio_duration: float) -> str:
    """
    Combine video and audio using MoviePy with smooth transitions
    """
    # Validate inputs
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")
    if video_duration <= 0:
        raise ValueError(f"Invalid video duration: {video_duration}")
    if audio_duration <= 0:
        raise ValueError(f"Invalid audio duration: {audio_duration}")
    
    # Ensure output directory exists
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    try:
        # Load video and audio with error checking
        try:
            video = VideoFileClip(video_path)
            if not hasattr(video, 'duration') or video.duration is None:
                raise ValueError("Video clip has invalid duration")
        except Exception as e:
            raise RuntimeError(f"Failed to load video file: {str(e)}")
            
        try:
            audio = AudioFileClip(audio_path)
            if not hasattr(audio, 'duration') or audio.duration is None:
                raise ValueError("Audio clip has invalid duration")
        except Exception as e:
            if 'video' in locals():
                video.close()  # Clean up video if audio fails
            raise RuntimeError(f"Failed to load audio file: {str(e)}")
        
        if video_duration < audio_duration:
            # Create a list of video clips that will loop
            num_loops = int(audio_duration / video_duration) + 1
            video_clips = []
            
            try:
                # Create new instances of VideoFileClip for each loop
                for _ in range(num_loops):
                    try:
                        clip = VideoFileClip(video_path)
                        if not hasattr(clip, 'duration') or clip.duration is None:
                            raise ValueError("Video clip has invalid duration")
                        video_clips.append(clip)
                    except Exception as e:
                        # Clean up any clips we managed to create before the error
                        for created_clip in video_clips:
                            try:
                                created_clip.close()
                            except:
                                pass
                        raise RuntimeError(f"Failed to create video clip: {str(e)}")
                
                # Import required transition
                try:
                    # Simple concatenation without transitions
                    final_video = concatenate_videoclips(
                        video_clips,
                        method="chain"  # Use simpler chain method instead of compose
                    )
                except Exception as e:
                    raise RuntimeError(f"Failed to concatenate video clips: {str(e)}")
            finally:
                # Close all video clips
                for clip in video_clips:
                    try:
                        clip.close()
                    except:
                        pass
            
            # Trim to match audio duration
            final_video = final_video.subclip(0, audio_duration)
        else:
            # Just trim the video
            final_video = video.subclip(0, audio_duration)
        
        # Set audio
        final_video = final_video.set_audio(audio)
        
        # Write output with high quality
        final_video.write_videofile(
            output_path,
            codec='libx264',
            audio_codec='aac',
            temp_audiofile=output_path + ".temp-audio.m4a",
            remove_temp=True,
            bitrate="8000k"
        )
        
        # Close clips to release resources
        video.close()
        audio.close()
        final_video.close()
        
        return output_path
    except Exception as e:
        logger.error(f"Error combining video and audio: {str(e)}")
        raise

def concatenate_videos(video_paths: List[str], output_path: str) -> str:
    """
    Concatenate multiple videos using MoviePy with transitions
    """
    # Validate inputs
    if not video_paths:
        raise ValueError("No video paths provided for concatenation")
    for path in video_paths:
        if not os.path.exists(path):
            raise FileNotFoundError(f"Video file not found: {path}")
            
    # Ensure output directory exists
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    
    clips = []
    try:
        # Load all video clips with validation
        for path in video_paths:
            try:
                clip = VideoFileClip(path)
                if not hasattr(clip, 'duration') or clip.duration is None:
                    raise ValueError(f"Video clip has invalid duration: {path}")
                clips.append(clip)
            except Exception as e:
                # Clean up any clips we managed to load before the error
                for loaded_clip in clips:
                    try:
                        loaded_clip.close()
                    except:
                        pass
                raise RuntimeError(f"Failed to load video clip {path}: {str(e)}")
        
        final_video = None
        try:
            logger.info(f"Concatenating {len(clips)} clips with chain method")
            for i, clip in enumerate(clips):
                logger.info(f"Clip {i}: duration={clip.duration}, size={clip.size}")

            # Simple concatenation without transitions
            final_video = concatenate_videoclips(
                clips,
                method="chain"  # Use simpler chain method instead of compose
            )
            logger.info(f"Concatenation successful. Final duration: {final_video.duration}")

            if not hasattr(final_video, 'duration') or final_video.duration is None:
                raise ValueError("Concatenated video has invalid duration")
            
            # Write output with high quality
            final_video.write_videofile(
                output_path,
                codec='libx264',
                audio_codec='aac',
                temp_audiofile=output_path + ".temp-audio.m4a",
                remove_temp=True,
                bitrate="8000k"
            )
        except Exception as e:
            raise RuntimeError(f"Failed to concatenate video clips: {str(e)}")
        finally:
            # Clean up all resources
            for clip in clips:
                try:
                    clip.close()
                except:
                    pass
            if final_video:
                try:
                    final_video.close()
                except:
                    pass
        
        return output_path
    except Exception as e:
        logger.error(f"Error concatenating videos: {str(e)}")
        raise

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
    """
    scene_dir = os.path.join(LOCAL_STORAGE_PATH, job_id, f"scene_{scene_num}")
    os.makedirs(scene_dir, exist_ok=True)
    
    # Generate voice for scene
    audio_path = os.path.join(scene_dir, "voice.mp3")
    await synthesize_voice(scene, tts, voice, audio_path)

    # Verify that the audio file was created
    if not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
        err_msg = f"TTS failed to create a valid audio file at {audio_path} for scene: {scene_num}"
        logger.error(err_msg)
        raise FileNotFoundError(err_msg)
    
    # Get scene duration from audio
    audio_duration = get_media_duration(audio_path)
    
    # Try getting video in order: custom URL -> stock media -> placeholder
    video_url = None
    
    if custom_url:
        logger.info(f"Using custom URL for scene {scene_num}")
        video_url = custom_url
    else:
        # Try stock media with keywords
        keywords = get_scene_keywords(scene)
        stock_videos = await fetch_stock_media(" ".join(keywords))
        
        if stock_videos and stock_videos[0].get('video_files'):
            video_url = stock_videos[0]['video_files'][0]['link']
            logger.info(f"Using stock video for scene {scene_num}")
        elif use_placeholder:
            if placeholder_url:
                logger.warning(f"No stock videos found for scene {scene_num}, using provided placeholder URL")
                video_url = placeholder_url
            elif os.path.exists(DEFAULT_PLACEHOLDER_VIDEO):
                logger.warning(f"No stock videos found for scene {scene_num}, using default placeholder")
                video_url = DEFAULT_PLACEHOLDER_VIDEO
        else:
            raise Exception(f"No video source available for scene {scene_num}")
    
    raw_video_path = os.path.join(scene_dir, "raw_video.mp4")
    logger.info(f"Downloading/preparing video for scene {scene_num}")
    
    # Always download if it's not the local default placeholder
    if video_url != DEFAULT_PLACEHOLDER_VIDEO and video_url != os.path.abspath(DEFAULT_PLACEHOLDER_VIDEO):
        await download_media(video_url, raw_video_path)
    else:
        # Copy local placeholder video
        import shutil
        shutil.copy2(DEFAULT_PLACEHOLDER_VIDEO, raw_video_path)

    # Validate downloaded/copied video
    if not validate_video_file(raw_video_path):
        raise ValueError(f"Invalid or corrupted video file after download/copy for scene {scene_num}")
    
    # Crop video to aspect ratio
    cropped_video_path = os.path.join(scene_dir, "cropped_video.mp4")
    crop_video_to_aspect_ratio(raw_video_path, aspect_ratio, cropped_video_path)
    
    # Validate cropped video
    if not validate_video_file(cropped_video_path):
        raise ValueError(f"Invalid or corrupted video file after cropping for scene {scene_num}")
    
    # Get video duration
    video_duration = get_media_duration(cropped_video_path)
    
    # Combine video and audio
    scene_output_path = os.path.join(scene_dir, "final_scene.mp4")
    combine_video_audio(cropped_video_path, audio_path, scene_output_path, video_duration, audio_duration)
    
    # Cleanup
    os.remove(raw_video_path)
    os.remove(cropped_video_path)
    
    return scene_output_path

def format_ass_time(seconds):
    """Convert float seconds to ASS time format H:MM:SS.cc"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centiseconds = int(round((seconds - int(seconds)) * 100))
    return f"{hours}:{minutes:02}:{secs:02}.{centiseconds:02}"

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
    """
    try:
        # Reset the used_videos set for each new video processing
        global used_videos
        used_videos = set()
        
        # Create job directory
        job_dir = os.path.join(LOCAL_STORAGE_PATH, job_id)
        os.makedirs(job_dir, exist_ok=True)
        
        # Split script into scenes
        scenes = extract_scenes(script)
        if not scenes:
            raise Exception("No valid scenes found in script")
        
        # Process scenes in parallel with a semaphore to control concurrency
        async def process_all_scenes():
            # Limit concurrent scene processing to avoid memory issues
            semaphore = asyncio.Semaphore(3)  # Process up to 3 scenes at once
            
            # Create mapping of scene indices to custom URLs if provided
            custom_urls = {}
            if custom_media:
                custom_urls = {item['scene_index']: item['media_url'] 
                             for item in custom_media if 'scene_index' in item and 'media_url' in item}

            async def process_scene_with_retries(scene, index):
                # Use semaphore to limit concurrent processing
                async with semaphore:
                    return await with_retries(
                        process_scene,
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

            # Process all scenes concurrently
            tasks = [process_scene_with_retries(scene, i) for i, scene in enumerate(scenes)]
            scene_paths = await asyncio.gather(*tasks)
            
            return scene_paths

        # Run the parallel processing
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        scene_paths = loop.run_until_complete(process_all_scenes())
        
        # Combine all scenes
        final_path = os.path.join(job_dir, "final_video.mp4")
        concatenate_videos(scene_paths, final_path)
        
        # Add captions if requested
        if add_captions:
            # Transcribe final video
            model = whisper.load_model("base")
            transcription = model.transcribe(final_path)
            
            # Create temporary SRT file content
            srt_content = ""
            for i, segment in enumerate(transcription['segments'], 1):
                start_time_str = format_ass_time(segment['start'])
                end_time_str = format_ass_time(segment['end'])
                text = segment['text'].strip()
                srt_content += f"{i}\n{start_time_str.replace('.',',')} --> {end_time_str.replace('.',',')}\n{text}\n\n"
            
            # Apply captions using existing caption service, passing the content
            captioned_path = process_captioning_v1(
                final_path,          # video_url (local path)
                srt_content,         # captions (SRT content string)
                caption_settings,    # settings
                [],                  # replace (empty list as not supported here)
                job_id               # job_id
                # language defaults to 'auto'
            )
            
            # Cleanup original final video (captioned_path is the new final path)
            os.remove(final_path)
            final_path = captioned_path
        
        return final_path
        
    except Exception as e:
        logger.error(f"Error processing scripted video: {str(e)}")
        raise
