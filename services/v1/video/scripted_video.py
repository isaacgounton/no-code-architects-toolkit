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
import ffmpeg
import logging
import edge_tts
import asyncio
import json
import re
import nltk
from nltk.tokenize import word_tokenize
from nltk.tag import pos_tag
from typing import List, Dict, Any, Optional, Union
import aiohttp
from config import LOCAL_STORAGE_PATH, PEXELS_API_KEY, PIXABAY_API_KEY, DEFAULT_PLACEHOLDER_VIDEO
from services.v1.video.caption_video import process_captioning_v1, format_ass_time
import tempfile
import whisper
from nltk.corpus import stopwords
from services.v1.video.utils import format_ass_time

# Initialize logger
logger = logging.getLogger(__name__)

# Constants for video resolutions
RESOLUTIONS = {
    "16:9": (1920, 1080),
    "9:16": (1080, 1920),
    "1:1": (1080, 1080)
}

async def synthesize_voice(text: str, voice: str, output_path: str) -> str:
    """
    Synthesize voice from text using edge-tts
    """
    try:
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(output_path)
        return output_path
    except Exception as e:
        logger.error(f"Voice synthesis error: {str(e)}")
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

async def fetch_stock_media(query: str, media_type: str = "video", custom_url: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Fetch stock media with fallback options and custom URL support
    """
    if custom_url:
        # Return custom URL in a format compatible with the rest of the pipeline
        return [{
            "video_files" if media_type == "video" else "photos": [{
                "link": custom_url
            }]
        }]
    
    # Try Pexels first
    results = await fetch_from_pexels(query, media_type)
    if results:
        return results
    
    # If no results from Pexels, try Pixabay
    logger.info(f"No results from Pexels for '{query}', trying Pixabay")
    pixabay_results = await fetch_from_pixabay(query, media_type)
    if pixabay_results:
        # Convert Pixabay format to match Pexels format
        return [{
            "video_files" if media_type == "video" else "photos": [{
                "link": item.get("videos", {}).get("large", {}).get("url") if media_type == "video" else item.get("largeImageURL")
            }]
        } for item in pixabay_results]
    
    # If still no results, try with alternative keywords
    alt_keywords = generate_alternative_keywords(query)
    for alt_query in alt_keywords:
        logger.info(f"Trying alternative query: {alt_query}")
        # Try Pexels with alternative keywords
        results = await fetch_from_pexels(alt_query, media_type)
        if results:
            return results
        # Try Pixabay with alternative keywords
        pixabay_results = await fetch_from_pixabay(alt_query, media_type)
        if pixabay_results:
            return [{
                "video_files" if media_type == "video" else "photos": [{
                    "link": item.get("videos", {}).get("large", {}).get("url") if media_type == "video" else item.get("largeImageURL")
                }]
            } for item in pixabay_results]
    
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
    Split script into scenes based on paragraphs
    """
    # Split by double newlines to separate paragraphs
    scenes = [scene.strip() for scene in script.split("\n\n") if scene.strip()]
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
    Get duration of a media file using ffmpeg
    """
    probe = ffmpeg.probe(file_path)
    duration = float(probe['format']['duration'])
    return duration

def crop_video_to_aspect_ratio(video_path: str, target_ratio: str, output_path: str) -> str:
    """
    Crop video to desired aspect ratio
    """
    target_width, target_height = RESOLUTIONS[target_ratio]
    
    try:
        # Get video dimensions
        probe = ffmpeg.probe(video_path)
        video_info = next(s for s in probe['streams'] if s['codec_type'] == 'video')
        width = int(video_info['width'])
        height = int(video_info['height'])
        
        # Calculate crop dimensions
        current_ratio = width / height
        target_ratio_value = target_width / target_height
        
        if current_ratio > target_ratio_value:
            # Video is too wide, crop width
            new_width = int(height * target_ratio_value)
            crop_x = (width - new_width) // 2
            crop_y = 0
            crop_width = new_width
            crop_height = height
        else:
            # Video is too tall, crop height
            new_height = int(width / target_ratio_value)
            crop_x = 0
            crop_y = (height - new_height) // 2
            crop_width = width
            crop_height = new_height
        
        # Apply crop and resize
        stream = ffmpeg.input(video_path)
        stream = ffmpeg.crop(stream, crop_x, crop_y, crop_width, crop_height)
        stream = ffmpeg.filter(stream, 'scale', target_width, target_height)
        stream = ffmpeg.output(stream, output_path, acodec='copy')
        ffmpeg.run(stream, overwrite_output=True)
        
        return output_path
    except Exception as e:
        logger.error(f"Error cropping video: {str(e)}")
        raise

def combine_video_audio(video_path: str, audio_path: str, output_path: str, video_duration: float, audio_duration: float) -> str:
    """
    Combine video and audio, handling looping if needed
    """
    try:
        if video_duration < audio_duration:
            # Create a complex filter to loop video
            num_loops = int(audio_duration / video_duration) + 1
            loop_filter = f"loop={num_loops}:1:0"
            video = ffmpeg.input(video_path).filter(loop_filter)
        else:
            video = ffmpeg.input(video_path)
        
        # Trim video to audio duration
        video = video.filter('trim', duration=audio_duration)
        audio = ffmpeg.input(audio_path)
        
        # Combine video and audio
        ffmpeg.output(
            video,
            audio,
            output_path,
            vcodec='libx264',
            acodec='aac',
            strict='experimental'
        ).overwrite_output().run()
        
        return output_path
    except Exception as e:
        logger.error(f"Error combining video and audio: {str(e)}")
        raise

def concatenate_videos(video_paths: List[str], output_path: str) -> str:
    """
    Concatenate multiple videos using ffmpeg
    """
    try:
        # Create a temporary file listing all videos to concatenate
        with tempfile.NamedTemporaryFile('w', suffix='.txt', delete=False) as f:
            for video_path in video_paths:
                f.write(f"file '{os.path.abspath(video_path)}'\n")
            concat_list = f.name
        
        # Run ffmpeg concatenation
        ffmpeg.input(
            concat_list,
            format='concat',
            safe=0
        ).output(
            output_path,
            c='copy'
        ).overwrite_output().run()
        
        # Clean up
        os.unlink(concat_list)
        return output_path
    except Exception as e:
        logger.error(f"Error concatenating videos: {str(e)}")
        raise

async def process_scene(
    scene: str, 
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
    await synthesize_voice(scene, voice, audio_path)
    
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
    # Always download if it's not the local default placeholder
    
    # Debugging: Check if DEFAULT_PLACEHOLDER_VIDEO is in globals
    logger.info(f"Globals check before line 380: {'DEFAULT_PLACEHOLDER_VIDEO' in globals()}")
    logger.info(f"Value if present: {globals().get('DEFAULT_PLACEHOLDER_VIDEO', 'Not Found')}")

    if video_url != DEFAULT_PLACEHOLDER_VIDEO:
        await download_media(video_url, raw_video_path)
    else:
        # Copy local placeholder video
        import shutil
        shutil.copy2(DEFAULT_PLACEHOLDER_VIDEO, raw_video_path)
    
    # Crop video to aspect ratio
    cropped_video_path = os.path.join(scene_dir, "cropped_video.mp4")
    crop_video_to_aspect_ratio(raw_video_path, aspect_ratio, cropped_video_path)
    
    # Get video duration
    video_duration = get_media_duration(cropped_video_path)
    
    # Combine video and audio
    scene_output_path = os.path.join(scene_dir, "final_scene.mp4")
    combine_video_audio(cropped_video_path, audio_path, scene_output_path, video_duration, audio_duration)
    
    # Cleanup
    os.remove(raw_video_path)
    os.remove(cropped_video_path)
    
    return scene_output_path

def process_scripted_video_v1(
    script: str,
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
        # Create job directory
        job_dir = os.path.join(LOCAL_STORAGE_PATH, job_id)
        os.makedirs(job_dir, exist_ok=True)
        
        # Split script into scenes
        scenes = extract_scenes(script)
        if not scenes:
            raise Exception("No valid scenes found in script")
        
        # Process each scene asynchronously
        scene_paths = []
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Create mapping of scene indices to custom URLs if provided
        custom_urls = {}
        if custom_media:
            custom_urls = {item['scene_index']: item['media_url'] 
                         for item in custom_media if 'scene_index' in item and 'media_url' in item}
        
        for i, scene in enumerate(scenes):
            # Get custom URL for this scene if available
            custom_url = custom_urls.get(i)
            
            scene_path = loop.run_until_complete(
                process_scene(
                    scene=scene,
                    voice=voice,
                    aspect_ratio=aspect_ratio,
                    job_id=job_id,
                    scene_num=i,
                    custom_url=custom_url,
                    use_placeholder=use_placeholder,
                    placeholder_url=placeholder_url
                )
            )
            scene_paths.append(scene_path)
        
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
