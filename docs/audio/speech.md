# TTS (Text-to-Speech) API Endpoint Documentation

**Implemented by:** [Harrison Fisher](https://github.com/HarrisonFisher)

## Overview

The `/v1/audio/speech` endpoint allows clients to convert text into speech using different Text-to-Speech (TTS) engines. The service supports `edge-tts`, `streamlabs-polly`, and `kokoro` as TTS providers, offering flexibility in the choice of voices and speech synthesis options. It integrates with the application's queuing system to manage potentially time-consuming operations, ensuring smooth processing of requests.

## Endpoints

### List Available Voices
- **URL**: `/v1/audio/speech/voices`
- **Method**: `GET`
- **Description**: Returns a list of all available voices across all TTS engines

### Generate Speech
- **URL**: `/v1/audio/speech`
- **Method**: `POST`
- **Description**: Converts text to speech with optional voice and adjustment parameters

## Request

### Headers

- `x-api-key`: Required. Your API authentication key.

### Body Parameters

| Parameter     | Type   | Required | Description |
|---------------|--------|----------|-------------|
| `tts`         | String | No       | The TTS engine to use. Default is `edge-tts`. Options: `edge-tts`, `streamlabs-polly`, `kokoro` |
| `text`        | String | Yes      | The text to convert to speech. |
| `voice`       | String | No       | The voice to use. The valid voice list depends on the TTS engine. |
| `rate`        | String | No       | Speech rate adjustment (e.g., "+50%", "-20%"). Format: ^[+-]\\d+%$ |
| `volume`      | String | No       | Volume adjustment (e.g., "+50%", "-20%"). Format: ^[+-]\\d+%$ |
| `pitch`       | String | No       | Pitch adjustment in Hz (e.g., "+50Hz", "-20Hz"). Format: ^[+-]\\d+Hz$ |
| `webhook_url` | String | No       | A URL to receive a callback notification when processing is complete. |
| `id`          | String | No       | A custom identifier for tracking the request. |

### Example Request

```json
{
  "tts": "edge-tts",
  "text": "Hello, world!",
  "voice": "en-US-AvaNeural",
  "rate": "+10%",
  "volume": "+20%",
  "pitch": "+5Hz",
  "webhook_url": "https://your-webhook-endpoint.com/callback",
  "id": "custom-request-id-123"
}
```

### Example cURL Command

```bash
curl -X POST \
  https://api.example.com/v1/audio/speech \
  -H 'Content-Type: application/json' \
  -H 'x-api-key: your-api-key-here' \
  -d '{
    "tts": "edge-tts",
    "text": "Hello, world!",
    "voice": "en-US-AvaNeural",
    "rate": "+10%",
    "volume": "+20%",
    "pitch": "+5Hz",
    "webhook_url": "https://your-webhook-endpoint.com/callback",
    "id": "custom-request-id-123"
  }'
```

## Response

### List Voices Response

```json
{
  "voices": [
    {
      "name": "en-US-AvaNeural",
      "gender": "Female",
      "locale": "en-US",
      "engine": "edge-tts"
    },
    {
      "name": "Brian",
      "locale": "en-US",
      "engine": "streamlabs-polly"
    }
  ]
}
```

### Synchronous Response (No webhook\_url provided)

```json
{
  "code": 200,
  "id": "custom-request-id-123",
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "response": {
    "audio_url": "https://storage.example.com/audio-file.mp3",
    "subtitle_url": "https://storage.example.com/subtitle-file.srt"
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

### Asynchronous Response (webhook\_url provided)

Initial response:
```json
{
  "code": 202,
  "id": "custom-request-id-123",
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "processing",
  "pid": 12345,
  "queue_id": 67890,
  "max_queue_length": "unlimited",
  "queue_length": 1,
  "build_number": "1.0.123"
}
```

Webhook payload:
```json
{
  "endpoint": "/v1/audio/speech",
  "code": 200,
  "id": "custom-request-id-123",
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "response": {
    "audio_url": "https://storage.example.com/audio-file.mp3",
    "subtitle_url": "https://storage.example.com/subtitle-file.srt"
  },
  "message": "success",
  "pid": 12345,
  "queue_id": 67890,
  "run_time": 3.456,
  "queue_time": 1.234,
  "total_time": 4.690,
  "queue_length": 0,
  "build_number": "1.0.123"
}
```

## Error Handling

* **Missing Required Parameters**: If `text` is missing or empty, a 400 Bad Request response will be returned.
* **Invalid TTS Engine**: If the `tts` parameter is invalid, a 400 Bad Request response will be returned.
* **Invalid Adjustments**: If rate, volume, or pitch values don't match the required format, a 400 Bad Request response will be returned.
* **Authentication Failure**: If the API key is invalid or missing, a 401 Unauthorized response will be returned.
* **Queue Limit**: If the queue is full (when MAX\_QUEUE\_LENGTH is set), a 429 Too Many Requests response will be returned.
* **Processing Errors**: Any errors during text processing, speech synthesis, or audio file generation will result in a 500 Internal Server Error response.

## TTS Engine Features

### edge-tts
- Supports extensive voice list in multiple languages
- Full support for rate, volume, and pitch adjustments
- Outputs MP3 format
- Preview voices at: https://tts.travisvn.com/

### streamlabs-polly
- High-quality voices based on Amazon Polly
- Limited support for adjustments
- Outputs MP3 format
- Available voices: Brian, Emma, Russell, Joey, Matthew, Joanna, Kimberly, Amy, Geraint, Nicole, Justin, Ivy, Kendra, Salli, Raveena

### kokoro
- Uses Kokoro-82M model with ONNX runtime
- English language support
- Outputs WAV format
- Voice list available at: https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md

## Additional Features

1. **Subtitle Generation**: All TTS requests automatically generate an SRT subtitle file.
2. **Text Chunking**: Long texts are automatically chunked and processed in parts for better handling.
3. **Rate Limiting**: Built-in rate limiting protection with automatic retry mechanism.
4. **Cloud Storage**: Generated audio and subtitle files are automatically uploaded to cloud storage.

## Best Practices

1. **Voice Selection**: Use the `/v1/audio/speech/voices` endpoint to get the list of available voices for each engine.
2. **Asynchronous Processing**: For longer texts, use the webhook approach to avoid timeouts.
3. **Adjustments**: Start with small adjustments (e.g., ±10%) and test the results.
4. **Subtitle Usage**: Use the generated subtitles for accessibility and synchronization.
5. **Error Handling**: Implement robust error handling for various HTTP status codes.
6. **Rate Limits**: Be mindful of rate limits, especially with streamlabs-polly.
