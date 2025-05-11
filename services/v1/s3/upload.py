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
import boto3
import logging
import requests
from urllib.parse import urlparse, unquote, quote
import uuid
from werkzeug.utils import secure_filename

logger = logging.getLogger(__name__)

def get_s3_client():
    """Create and return an S3 client using environment variables."""
    endpoint_url = os.getenv('S3_ENDPOINT_URL')
    access_key = os.getenv('S3_ACCESS_KEY')
    secret_key = os.getenv('S3_SECRET_KEY')
    region = os.environ.get('S3_REGION', '')
    
    session = boto3.Session(
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region
    )
    
    return session.client('s3', endpoint_url=endpoint_url)

def secure_filename_with_extension(filename):
    """
    Create a secure filename while preserving the original file extension.
    
    Args:
        filename (str): Original filename
    
    Returns:
        str: Secure filename with original extension
    """
    if not filename:
        return f"{uuid.uuid4()}"
    
    # Split filename into name and extension
    base, ext = os.path.splitext(filename)
    # Secure the base filename
    secure_base = secure_filename(base)
    
    # If after securing the base is empty, use a UUID
    if not secure_base:
        secure_base = str(uuid.uuid4())
    
    # Return combination of secured base and original extension
    return f"{secure_base}{ext.lower()}"

def get_filename_from_url(url):
    """Extract filename from URL."""
    path = urlparse(url).path
    filename = os.path.basename(unquote(path))
    
    return secure_filename_with_extension(filename)

def stream_upload_to_s3(source, custom_filename=None, make_public=False, is_url=True):
    """
    Stream content to S3 using multipart upload. Can handle both URL and file uploads.
    
    Args:
        source: Either a URL string or a FileStorage object
        custom_filename (str, optional): Custom filename for the uploaded file
        make_public (bool, optional): Whether to make the file publicly accessible
        is_url (bool): Whether the source is a URL (True) or file upload (False)
    
    Returns:
        dict: Information about the uploaded file
    """
    try:
        # Get S3 configuration
        bucket_name = os.environ.get('S3_BUCKET_NAME', '')
        endpoint_url = os.getenv('S3_ENDPOINT_URL')
        
        # Get S3 client
        s3_client = get_s3_client()
        
        # Determine filename
        if custom_filename:
            filename = secure_filename_with_extension(custom_filename)
        elif is_url:
            filename = get_filename_from_url(source)
        else:
            filename = secure_filename_with_extension(source.filename)
        
        # Start a multipart upload
        logger.info(f"Starting multipart upload for {filename} to bucket {bucket_name}")
        acl = 'public-read' if make_public else 'private'
        
        multipart_upload = s3_client.create_multipart_upload(
            Bucket=bucket_name,
            Key=filename,
            ACL=acl
        )
        
        upload_id = multipart_upload['UploadId']
        chunk_size = 5 * 1024 * 1024  # 5MB chunks (AWS minimum)
        parts = []
        part_number = 1
        
        if is_url:
            # Stream from URL
            response = requests.get(source, stream=True)
            response.raise_for_status()
            
            buffer = bytearray()
            for chunk in response.iter_content(chunk_size=1024 * 1024):  # 1MB read chunks
                buffer.extend(chunk)
                
                # When we have enough data for a part, upload it
                if len(buffer) >= chunk_size:
                    logger.info(f"Uploading part {part_number}")
                    part = s3_client.upload_part(
                        Bucket=bucket_name,
                        Key=filename,
                        PartNumber=part_number,
                        UploadId=upload_id,
                        Body=buffer
                    )
                    
                    parts.append({
                        'PartNumber': part_number,
                        'ETag': part['ETag']
                    })
                    
                    part_number += 1
                    buffer = bytearray()
            
            # Upload any remaining data
            if buffer:
                logger.info(f"Uploading final part {part_number}")
                part = s3_client.upload_part(
                    Bucket=bucket_name,
                    Key=filename,
                    PartNumber=part_number,
                    UploadId=upload_id,
                    Body=buffer
                )
                
                parts.append({
                    'PartNumber': part_number,
                    'ETag': part['ETag']
                })
        else:
            # Stream from file
            while True:
                chunk = source.read(chunk_size)
                if not chunk:
                    break
                    
                logger.info(f"Uploading part {part_number}")
                part = s3_client.upload_part(
                    Bucket=bucket_name,
                    Key=filename,
                    PartNumber=part_number,
                    UploadId=upload_id,
                    Body=chunk
                )
                
                parts.append({
                    'PartNumber': part_number,
                    'ETag': part['ETag']
                })
                
                part_number += 1
        
        # Complete the multipart upload
        logger.info("Completing multipart upload")
        s3_client.complete_multipart_upload(
            Bucket=bucket_name,
            Key=filename,
            UploadId=upload_id,
            MultipartUpload={'Parts': parts}
        )
        
        # Generate the URL to the uploaded file
        if make_public:
            # URL encode the filename for the URL only
            encoded_filename = quote(filename)
            file_url = f"{endpoint_url}/{bucket_name}/{encoded_filename}"
        else:
            # Generate a pre-signed URL for private files
            file_url = s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': bucket_name, 'Key': filename},
                ExpiresIn=3600  # URL expires in 1 hour
            )
        
        return {
            'file_url': file_url,
            'filename': filename,
            'bucket': bucket_name,
            'public': make_public
        }
        
    except Exception as e:
        logger.error(f"Error streaming to S3: {e}")
        raise
