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

from flask import Blueprint, request, jsonify, current_app # Added current_app
# from services.authentication import authenticate # Removed
# from app_utils import validate_payload, queue_task_wrapper # queue_task_wrapper removed, validate_payload not used
from services.v1.s3.upload import stream_upload_to_s3
import os
import json
import logging

logger = logging.getLogger(__name__)
v1_s3_upload_bp = Blueprint('v1_s3_upload', __name__)

@v1_s3_upload_bp.route('/v1/s3/upload', methods=['POST'])
# @authenticate # Removed
@current_app.queue_task(bypass_queue=False) # Changed decorator
def s3_upload_endpoint(job_id, data):
    # The API key check is now handled by the @current_app.queue_task decorator
    try:
        # Check if a file was uploaded
        if 'file' in request.files:
            file = request.files['file']
            if file.filename == '':
                return "No selected file", "/v1/s3/upload", 400
            
            # Get optional parameters from form data
            filename = request.form.get('filename')  # Optional custom filename
            make_public = request.form.get('public', 'false').lower() == 'true'  # Default to private
            
            logger.info(f"Job {job_id}: Starting S3 file upload for {file.filename}")
            
            result = stream_upload_to_s3(file, filename, make_public, is_url=False)
            
        # Check if a URL was provided in JSON data
        elif request.is_json and data.get('file_url'):
            file_url = data.get('file_url')
            filename = data.get('filename')  # Optional, will default to URL filename
            make_public = data.get('public', False)  # Default to private
            
            logger.info(f"Job {job_id}: Starting S3 streaming upload from {file_url}")
            
            result = stream_upload_to_s3(file_url, filename, make_public, is_url=True)
            
        else:
            return "No file uploaded and no URL provided", "/v1/s3/upload", 400
        
        logger.info(f"Job {job_id}: Successfully uploaded to S3")
        
        return result, "/v1/s3/upload", 200
        
    except Exception as e:
        logger.error(f"Job {job_id}: Error uploading to S3 - {str(e)}")
        return str(e), "/v1/s3/upload", 500
