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
import requests
import json
from typing import Dict, Any, Optional, List

class ChatCompletionError(Exception):
    """Custom exception for chat completion errors"""
    pass

class ChatService:
    def __init__(self):
        self.base_url = os.environ.get('OLLAMA_BASE_URL', 'http://localhost:11434')
        self.model = "qwen:1.7b"

    def generate_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False
    ) -> Dict[str, Any]:
        """
        Generate a chat completion using Qwen 1.7B through Ollama.
        
        Args:
            messages: List of message dictionaries with 'role' and 'content'
            temperature: Controls randomness (0-1)
            max_tokens: Maximum number of tokens to generate
            stream: Whether to stream the response
            
        Returns:
            Dict containing the completion response
        """
        try:
            # Format messages for Ollama API
            formatted_messages = []
            for msg in messages:
                if msg['role'] not in ['system', 'user', 'assistant']:
                    raise ChatCompletionError(f"Invalid message role: {msg['role']}")
                formatted_messages.append({
                    'role': msg['role'],
                    'content': msg['content']
                })

            # Prepare the request payload
            payload = {
                'model': self.model,
                'messages': formatted_messages,
                'stream': stream,
                'options': {
                    'temperature': temperature
                }
            }

            if max_tokens:
                payload['options']['num_predict'] = max_tokens

            # Make the API request
            response = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                stream=stream
            )

            if not response.ok:
                raise ChatCompletionError(f"Ollama API error: {response.text}")

            if stream:
                return response.iter_lines()
            else:
                result = response.json()
                return {
                    'id': 'chat_' + os.urandom(4).hex(),
                    'object': 'chat.completion',
                    'created': result.get('created', 0),
                    'model': self.model,
                    'choices': [{
                        'index': 0,
                        'message': {
                            'role': 'assistant',
                            'content': result['message']['content']
                        },
                        'finish_reason': result.get('done', True) and 'stop' or 'length'
                    }],
                    'usage': result.get('usage', {
                        'prompt_tokens': 0,
                        'completion_tokens': 0,
                        'total_tokens': 0
                    })
                }

        except requests.exceptions.RequestException as e:
            raise ChatCompletionError(f"Network error: {str(e)}")
        except json.JSONDecodeError:
            raise ChatCompletionError("Invalid JSON response from Ollama API")
        except Exception as e:
            raise ChatCompletionError(f"Unexpected error: {str(e)}")
