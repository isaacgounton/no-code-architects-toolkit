# Chat Completions API Endpoint Documentation

## Overview

The `/v1/chat/completions` endpoint enables interaction with the Qwen 1.7B language model through Ollama. This endpoint supports both streaming and non-streaming responses, allowing for real-time chat interactions and conventional request-response patterns. The service is integrated with the application's queuing system for efficient handling of concurrent requests.

## Endpoints

### Generate Chat Completion
- **URL**: `/v1/chat/completions`
- **Method**: `POST`
- **Description**: Generates a chat completion response using the Qwen 1.7B model

## Request

### Headers

- `x-api-key`: Required. Your API authentication key.

### Body Parameters

| Parameter     | Type    | Required | Description |
|---------------|---------|----------|-------------|
| `messages`    | Array   | Yes      | Array of message objects containing the conversation history |
| `temperature` | Float   | No       | Controls randomness in the response (0-1). Default: 0.7 |
| `max_tokens`  | Integer | No       | Maximum number of tokens to generate |
| `stream`      | Boolean | No       | Whether to stream the response. Default: false |
| `id`          | String  | No       | A custom identifier for tracking the request |

#### Message Object Format

| Field     | Type   | Required | Description |
|-----------|--------|----------|-------------|
| `role`    | String | Yes      | The role of the message sender. Options: "system", "user", "assistant" |
| `content` | String | Yes      | The content of the message |

### Example Request

```json
{
  "messages": [
    {
      "role": "system",
      "content": "You are a helpful assistant."
    },
    {
      "role": "user",
      "content": "What is machine learning?"
    }
  ],
  "temperature": 0.7,
  "max_tokens": 500,
  "stream": false,
  "id": "custom-request-id-123"
}
```

### Example cURL Command

```bash
curl -X POST \
  https://api.example.com/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -H 'x-api-key: your-api-key-here' \
  -d '{
    "messages": [
      {
        "role": "system",
        "content": "You are a helpful assistant."
      },
      {
        "role": "user",
        "content": "What is machine learning?"
      }
    ],
    "temperature": 0.7
  }'
```

## Response

### Standard Response

```json
{
  "code": 200,
  "id": "custom-request-id-123",
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "response": {
    "id": "chat_abc123",
    "object": "chat.completion",
    "created": 1621845122,
    "model": "qwen:1.7b",
    "choices": [{
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Machine learning is a branch of artificial intelligence..."
      },
      "finish_reason": "stop"
    }],
    "usage": {
      "prompt_tokens": 24,
      "completion_tokens": 156,
      "total_tokens": 180
    }
  },
  "message": "success",
  "run_time": 2.345,
  "queue_time": 0,
  "total_time": 2.345,
  "pid": 12345,
  "queue_id": 67890,
  "queue_length": 0,
  "build_number": "1.0.123"
}
```

### Streaming Response

When `stream: true`, the response is sent as a stream of server-sent events (SSE):

```
data: {"id":"chat_abc123","choices":[{"delta":{"role":"assistant","content":"Machine"},"index":0}]}

data: {"id":"chat_abc123","choices":[{"delta":{"content":" learning"},"index":0}]}

data: {"id":"chat_abc123","choices":[{"delta":{"content":" is"},"index":0}]}

...

data: [DONE]
```


## Error Handling

* **Missing Required Parameters**: If `messages` array is missing or empty, a 400 Bad Request response will be returned.
* **Invalid Message Format**: If message objects don't contain required fields or have invalid roles, a 400 Bad Request response will be returned.
* **Invalid Temperature**: If temperature is not between 0 and 1, a 400 Bad Request response will be returned.
* **Invalid Max Tokens**: If max_tokens is not a positive integer, a 400 Bad Request response will be returned.
* **Authentication Failure**: If the API key is invalid or missing, a 401 Unauthorized response will be returned.
* **Queue Limit**: If the queue is full (when MAX_QUEUE_LENGTH is set), a 429 Too Many Requests response will be returned.
* **Model Error**: If there's an error with the language model or Ollama service, a 500 Internal Server Error response will be returned.

## Additional Features

1. **Streaming Support**: Real-time response streaming for interactive chat applications.
2. **Queue Management**: Automatic queue management for handling concurrent requests.
3. **Model Configuration**: Temperature and max_tokens parameters for controlling response generation.

## Best Practices

1. **Context Management**: Keep the messages array focused and relevant. Remove unnecessary context to save tokens.
2. **Temperature Setting**: Use lower temperatures (0.1-0.3) for factual responses, higher (0.7-0.9) for creative ones.
3. **Streaming**: Use streaming for chat interfaces to provide real-time responses.
4. **Error Handling**: Implement robust error handling for various HTTP status codes.
5. **Rate Limits**: Be mindful of rate limits and implement appropriate retry mechanisms.

## Model Information

The endpoint uses the Qwen 1.7B model, which is a powerful yet efficient language model that offers:
- Good performance on both English and Chinese text
- Efficient response generation
- Support for various tasks including chat, Q&A, and text generation
