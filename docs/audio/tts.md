# Text-to-Speech API

This endpoint provides text-to-speech synthesis using the Edge TTS engine.

## List Available Voices

Get a list of all available voices with their properties.

```
GET /v1/audio/tts/voices
```

### Response

```json
{
    "voices": [
        {
            "name": "en-US-JennyNeural",
            "gender": "Female",
            "categories": "General",
            "personalities": "Friendly, Positive"
        }
    ]
}
```

## Generate Speech

Convert text to speech using a specified voice.

```
POST /v1/audio/tts/generate
```

### Request Body

```json
{
    "text": "Text to convert to speech",
    "voice": "en-US-JennyNeural",
    "rate": "+0%",           // Optional: Speech rate adjustment
    "volume": "+0%",         // Optional: Volume adjustment
    "pitch": "+0Hz",         // Optional: Pitch adjustment
    "webhook_url": "https://your-webhook.com/callback",  // Optional
    "id": "your-custom-id"   // Optional
}
```

| Field | Type | Description |
|-------|------|-------------|
| text | string | The text to convert to speech |
| voice | string | The voice ID to use (from /voices endpoint) |
| rate | string | Optional: Speech rate adjustment (e.g. "+50%", "-50%"). Use negative values to slow down, positive to speed up |
| volume | string | Optional: Volume adjustment (e.g. "+50%", "-50%"). Use negative values to decrease, positive to increase |
| pitch | string | Optional: Pitch adjustment (e.g. "+50Hz", "-50Hz"). Use negative values to lower pitch, positive to raise it |
| webhook_url | string | Optional webhook URL for job completion notification |
| id | string | Optional custom identifier for tracking |

### Response

```json
{
    "audio_url": "https://storage.example.com/path/to/speech.mp3",
    "subtitle_url": "https://storage.example.com/path/to/speech.srt"
}
```

### Output Formats

- **Audio**: Generated as MP3 format
- **Subtitles**: Generated as SRT (SubRip) format, containing timing information for each spoken phrase

### Supported Voices

The following voices are available:

| Voice ID | Gender | Categories | Personalities |
|----------|--------|------------|---------------|
| af-ZA-AdriNeural | Female | General | Friendly, Positive |
| af-ZA-WillemNeural | Male | General | Friendly, Positive |
| am-ET-AmehaNeural | Male | General | Friendly, Positive |
| am-ET-MekdesNeural | Female | General | Friendly, Positive |
| ar-AE-FatimaNeural | Female | General | Friendly, Positive |
| ar-AE-HamdanNeural | Male | General | Friendly, Positive |
| ar-BH-AliNeural | Male | General | Friendly, Positive |
| ar-BH-LailaNeural | Female | General | Friendly, Positive |
| ar-DZ-AminaNeural | Female | General | Friendly, Positive |
| ar-DZ-IsmaelNeural | Male | General | Friendly, Positive |
| ar-EG-SalmaNeural | Female | General | Friendly, Positive |

And many more. Use the `/v1/audio/tts/voices` endpoint to get the complete, up-to-date list of available voices.

### Error Handling

The API uses standard HTTP status codes:

- 200: Success
- 202: Job accepted and being processed
- 400: Invalid request (missing/invalid parameters)
- 401: Unauthorized (invalid/missing authentication)
- 429: Too many requests (queue full)
- 500: Server error

### Webhook Notification

If a webhook_url is provided, it will receive a POST request with the job result:

```json
{
    "endpoint": "/v1/audio/tts/generate",
    "code": 200,
    "id": "your-custom-id",
    "job_id": "generated-job-id",
    "response": {
        "audio_url": "https://storage.example.com/path/to/speech.mp3",
        "subtitle_url": "https://storage.example.com/path/to/speech.srt"
    },
    "message": "success",
    "run_time": 1.234,
    "queue_time": 0.123,
    "total_time": 1.357,
    "queue_length": 0,
    "build_number": "current-build-number"
}
```

### Examples

1. Basic speech generation:
```bash
curl -X POST http://localhost:8080/v1/audio/tts/generate \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Hello world",
    "voice": "en-US-JennyNeural"
  }'
```

2. Speech with rate and pitch adjustment:
```bash
curl -X POST http://localhost:8080/v1/audio/tts/generate \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Hello world",
    "voice": "en-US-JennyNeural",
    "rate": "-20%",
    "pitch": "+10Hz"
  }'
```

3. Arabic text with Arabic voice:
```bash
curl -X POST http://localhost:8080/v1/audio/tts/generate \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "مرحبا كيف حالك؟",
    "voice": "ar-EG-SalmaNeural"
  }'
```

4. Speech with volume adjustment and webhook:
```bash
curl -X POST http://localhost:8080/v1/audio/tts/generate \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Hello world",
    "voice": "en-US-JennyNeural",
    "volume": "+20%",
    "webhook_url": "https://your-webhook.com/callback"
  }'
