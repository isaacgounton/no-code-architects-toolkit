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

from flask import Blueprint, request, Response, stream_with_context
from services.v1.chat.completions import ChatService, ChatCompletionError
from typing import Tuple, Union, Dict, Any
import time

# Create blueprint
v1_chat_completions_bp = Blueprint('v1_chat_completions', __name__)

def validate_request(data: Dict) -> Tuple[Union[Dict[str, Any], str], int]:
    """Validate the chat completion request data"""
    # Validate required fields
    if not isinstance(data, dict):
        return "Invalid request data", 400

    if 'messages' not in data:
        return "Missing required field: messages", 400
    
    if not isinstance(data['messages'], list) or not data['messages']:
        return "Messages must be a non-empty array", 400
    
    # Validate message format
    for msg in data['messages']:
        if not isinstance(msg, dict):
            return "Each message must be an object", 400
        if 'role' not in msg or 'content' not in msg:
            return "Each message must have 'role' and 'content' fields", 400
        if not isinstance(msg['content'], str):
            return "Message content must be a string", 400
        if msg['role'] not in ['system', 'user', 'assistant']:
            return f"Invalid role: {msg['role']}", 400
    
    # Validate optional parameters
    if 'temperature' in data:
        try:
            temp = float(data['temperature'])
            if not 0 <= temp <= 1:
                return "Temperature must be between 0 and 1", 400
        except ValueError:
            return "Temperature must be a number between 0 and 1", 400
    
    if 'max_tokens' in data:
        try:
            max_tokens = int(data['max_tokens'])
            if max_tokens <= 0:
                return "max_tokens must be a positive integer", 400
        except ValueError:
            return "max_tokens must be a positive integer", 400
    
    return data, 200

@v1_chat_completions_bp.route('/v1/chat/completions', methods=['POST'])
def chat_completion() -> Union[Response, Tuple[Dict[str, Any], int]]:
    """
    Handle chat completion requests
    
    Returns:
        Either a streaming response or a tuple containing the response data and status code
    """
    if not request.is_json:
        return "Request must be JSON", 400

    # Get and validate request data
    data = request.get_json()
    validated_data, status = validate_request(data)
    if status != 200:
        return validated_data, status
    
    try:
        # Initialize chat service
        chat_service = ChatService()
        
        # Extract parameters
        stream = data.get('stream', False)
        temperature = data.get('temperature', 0.7)
        max_tokens = data.get('max_tokens', None)
        
        if stream:
            def generate():
                try:
                    for line in chat_service.generate_completion(
                        messages=data['messages'],
                        temperature=temperature,
                        max_tokens=max_tokens,
                        stream=True
                    ):
                        if line:
                            yield f"data: {line.decode()}\n\n"
                except Exception as e:
                    yield f"data: {{\"error\": \"{str(e)}\"}}\n\n"
                yield "data: [DONE]\n\n"
            
            return Response(
                stream_with_context(generate()),
                mimetype='text/event-stream'
            )
        
        # Generate completion
        response = chat_service.generate_completion(
            messages=data['messages'],
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False
        )
        
        return response, 200
        
    except ChatCompletionError as e:
        return str(e), 400
    except Exception as e:
        return f"Internal server error: {str(e)}", 500
