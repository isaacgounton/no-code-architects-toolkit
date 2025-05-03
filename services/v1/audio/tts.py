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
import subprocess
from typing import Tuple, List, Dict, Optional
import json
from config import LOCAL_STORAGE_PATH

def list_voices() -> List[Dict[str, str]]:
    """Get list of available voices from edge-tts
    
    Returns:
        List of dictionaries containing voice information with keys:
        - name: Voice identifier (e.g. 'en-US-JennyNeural')
        - gender: Voice gender
        - categories: Content categories the voice is suitable for
        - personalities: Voice personality traits
    """
    try:
        result = subprocess.run(['edge-tts', '--list-voices'], 
                              capture_output=True, 
                              text=True)
        if result.returncode != 0:
            print(f"Failed to list voices: {result.stderr}")
            raise Exception(f"Failed to list voices: {result.stderr}")
            
        # Skip header line and parse remaining lines
        lines = result.stdout.strip().split('\n')[2:]  # Skip header row
        voices = []
        
        for line in lines:
            parts = line.split(None, 3)  # Split into max 4 parts
            if len(parts) >= 4:
                voice = {
                    'name': parts[0],
                    'gender': parts[1],
                    'categories': parts[2],
                    'personalities': parts[3]
                }
                voices.append(voice)
                
        print(f"Successfully retrieved {len(voices)} voices")
        return voices
    except Exception as e:
        print(f"Error listing voices: {str(e)}")
        raise Exception(f"Error listing voices: {str(e)}")

def generate_speech(
    text: str, 
    voice: str, 
    job_id: str, 
    rate: Optional[str] = None,
    volume: Optional[str] = None,
    pitch: Optional[str] = None
) -> Tuple[str, str]:
    """Generate speech from text using edge-tts
    
    Args:
        text: Text to convert to speech
        voice: Voice name to use (e.g. 'en-US-JennyNeural')
        job_id: Unique identifier for this job
        rate: Optional speech rate adjustment (e.g. '+50%', '-50%')
        volume: Optional volume adjustment (e.g. '+50%', '-50%')
        pitch: Optional pitch adjustment (e.g. '+50Hz', '-50Hz')
        
    Returns:
        Tuple containing paths to the generated audio and subtitle files
        
    Raises:
        Exception: If speech generation fails
    """
    try:
        # Create output paths using LOCAL_STORAGE_PATH
        output_dir = os.path.join(LOCAL_STORAGE_PATH, job_id)
        os.makedirs(output_dir, exist_ok=True)
        
        audio_file = os.path.join(output_dir, "speech.mp3")
        subtitle_file = os.path.join(output_dir, "speech.srt")

        # Build command with optional parameters
        cmd = ['edge-tts', '--voice', voice, '--text', text, 
               '--write-media', audio_file, '--write-subtitles', subtitle_file]
        
        if rate:
            cmd.extend(['--rate', rate])
        if volume:
            cmd.extend(['--volume', volume])
        if pitch:
            cmd.extend(['--pitch', pitch])

        # Run edge-tts command
        print(f"Generating speech for job {job_id} using voice {voice}")
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            print(f"TTS generation failed for job {job_id}: {result.stderr}")
            raise Exception(f"TTS generation failed: {result.stderr}")

        # Verify files were created
        if not os.path.exists(audio_file):
            raise FileNotFoundError(f"Audio file {audio_file} was not created")
        if not os.path.exists(subtitle_file):
            raise FileNotFoundError(f"Subtitle file {subtitle_file} was not created")

        print(f"Successfully generated speech files for job {job_id}")
        return audio_file, subtitle_file
        
    except Exception as e:
        print(f"Error generating speech for job {job_id}: {str(e)}")
        raise Exception(f"Error generating speech: {str(e)}")
