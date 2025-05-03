# Scripted Video Generation Endpoint (v1)

## 1. Overview

The `/v1/video/scripted` endpoint is part of the Video API and enables the generation of story-driven videos from natural language scripts. It combines stock footage, synthesized voiceovers, and automatic captioning to create professional-quality videos. The endpoint utilizes stock media APIs (Pexels, Pixabay), edge-tts for voice synthesis, and the existing captioning service to generate the final video.

## 2. Endpoint

**URL:** `/v1/video/scripted`
**Method:** `POST`

## 3. Request

### Headers

- `x-api-key`: Required. The API key for authentication.

### Body Parameters

The request body must be a JSON object with the following properties:

- `script` (string, required): The natural language script for the video. Each paragraph will be treated as a separate scene.
- `voice` (string, optional): The voice ID to use for narration (e.g., "en-US-AriaNeural"). Defaults to "en-US-AriaNeural".
- `aspect_ratio` (string, optional): The desired aspect ratio for the output video. Must be one of:
  - `16:9` (1920x1080, landscape)
  - `9:16` (1080x1920, vertical)
  - `1:1` (1080x1080, square)
  Defaults to "16:9".
- `add_captions` (boolean, optional): Whether to add captions to the video. Defaults to false.
- `caption_settings` (object, optional): Caption styling options when add_captions is true. See the /v1/video/caption endpoint documentation for available options.
- `webhook_url` (string, optional): A URL to receive a webhook notification when the video generation is complete.
- `id` (string, optional): An identifier for the request.
- `use_placeholder` (boolean, optional): Whether to use a placeholder video when no stock footage is found. Defaults to true.
- `placeholder_url` (string, optional): URL to a custom placeholder video to use when no stock footage is found.
- `custom_media` (array, optional): An array of objects specifying custom videos for specific scenes. Each object should have:
  - `scene_index` (number): The index of the scene to use this video for (0-based)
  - `media_url` (string): URL to the custom video to use for this scene

### Example Requests

#### Example 1: Basic Video Generation
```json
{
    "script": "3 tips to stay focused at work...\n\n1. Take regular breaks\nGive your mind time to reset every hour.\n\n2. Remove distractions\nTurn off notifications and find a quiet space.\n\n3. Use time blocking\nSchedule your tasks in focused blocks of time.",
    "voice": "en-US-AriaNeural",
    "aspect_ratio": "9:16"
}
```

#### Example 2: Video with Captions and Custom Settings
```json
{
    "script": "Welcome to our product demo...",
    "voice": "en-US-GuyNeural",
    "aspect_ratio": "16:9",
    "add_captions": true,
    "caption_settings": {
        "style": "classic",
        "line_color": "#FFFFFF",
        "outline_color": "#000000",
        "position": "bottom_center",
        "font_family": "Arial",
        "font_size": 24
    },
    "webhook_url": "https://example.com/webhook",
    "id": "product-demo-001"
}
```

#### Example 3: Video with Custom Media and Placeholder Settings
```json
{
    "script": "Our product workflow...\n\nStep 1: Planning\nStart with a clear plan.\n\nStep 2: Implementation\nExecute the plan effectively.",
    "voice": "en-US-AriaNeural",
    "aspect_ratio": "16:9",
    "custom_media": [
        {
            "scene_index": 0,
            "media_url": "https://example.com/intro-video.mp4"
        }
    ],
    "use_placeholder": true,
    "placeholder_url": "https://example.com/fallback-video.mp4"
}
```

```bash
curl -X POST \
     -H "x-api-key: YOUR_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{
        "script": "3 tips to stay focused at work...",
        "voice": "en-US-AriaNeural",
        "aspect_ratio": "9:16",
        "add_captions": true,
        "use_placeholder": true,
        "placeholder_url": "https://example.com/fallback.mp4"
     }' \
     https://your-api-endpoint.com/v1/video/scripted
```

## 4. Response

### Success Response

The response will be a JSON object with the following properties:

- `code` (integer): The HTTP status code (200 for success).
- `id` (string): The request identifier, if provided in the request.
- `job_id` (string): A unique identifier for the job.
- `video_url` (string): The cloud URL of the generated video.
- `duration` (number): The duration of the generated video in seconds.
- `message` (string): A success message.
- `pid` (integer): The process ID of the worker that processed the request.
- `queue_id` (integer): The ID of the queue used for processing the request.
- `run_time` (float): The time taken to process the request (in seconds).
- `queue_time` (float): The time the request spent in the queue (in seconds).
- `total_time` (float): The total time taken for the request (in seconds).
- `queue_length` (integer): The current length of the processing queue.
- `build_number` (string): The build number of the application.

Example:

```json
{
    "code": 200,
    "id": "product-demo-001",
    "job_id": "d290f1ee-6c54-4b01-90e6-d701748f0851",
    "video_url": "https://cloud.example.com/videos/product-demo.mp4",
    "duration": 76.5,
    "message": "success",
    "pid": 12345,
    "queue_id": 140682639937472,
    "run_time": 85.234,
    "queue_time": 0.012,
    "total_time": 85.246,
    "queue_length": 0,
    "build_number": "1.0.0"
}
```

### Error Responses

#### Missing or Invalid Parameters

**Status Code:** 400 Bad Request

```json
{
    "code": 400,
    "id": "product-demo-001",
    "job_id": "d290f1ee-6c54-4b01-90e6-d701748f0851",
    "message": "Missing or invalid parameters",
    "pid": 12345,
    "queue_id": 140682639937472,
    "queue_length": 0,
    "build_number": "1.0.0"
}
```

#### Invalid Aspect Ratio

**Status Code:** 400 Bad Request

```json
{
    "code": 400,
    "error": "Invalid aspect_ratio. Must be one of: 16:9, 9:16, 1:1",
    "pid": 12345,
    "queue_id": 140682639937472,
    "queue_length": 0,
    "build_number": "1.0.0"
}
```

#### Internal Server Error

**Status Code:** 500 Internal Server Error

```json
{
    "code": 500,
    "id": "product-demo-001",
    "job_id": "d290f1ee-6c54-4b01-90e6-d701748f0851",
    "error": "An unexpected error occurred during video generation.",
    "pid": 12345,
    "queue_id": 140682639937472,
    "queue_length": 0,
    "build_number": "1.0.0"
}
```

## 5. Error Handling

The endpoint handles the following common errors:

- **Missing or Invalid Parameters**: If any required parameters are missing or invalid, a 400 Bad Request error is returned with a descriptive error message.
- **Invalid Aspect Ratio**: If the provided aspect_ratio is not one of the supported values, a 400 Bad Request error is returned.
- **Stock Media API Error**: If there's an error fetching media from stock APIs, a 500 Internal Server Error is returned.
- **Voice Synthesis Error**: If there's an error generating the voiceover, a 500 Internal Server Error is returned.
- **Internal Server Error**: If an unexpected error occurs during video generation, a 500 Internal Server Error is returned with an error message.

## 6. Usage Notes

- The `script` parameter supports natural language text with paragraphs. Each paragraph is treated as a separate scene in the video.
- Supported aspect ratios:
  - `16:9` (1920x1080) - Standard landscape format
  - `9:16` (1080x1920) - Vertical video format
  - `1:1` (1080x1080) - Square format
- When `add_captions` is true, the system uses the same caption generation service as the `/v1/video/caption` endpoint.
- All caption styling options from the `/v1/video/caption` endpoint are supported through the `caption_settings` parameter.
- Videos are automatically scaled and cropped to match the requested aspect ratio while maintaining visual quality.
- Stock media is automatically selected based on keywords extracted from the script.
- Voice synthesis uses edge-tts, supporting multiple languages and voices.

## 7. Video Source Priority

The service follows this priority order when selecting video for each scene:

1. Custom video URL (if provided in custom_media for that scene)
2. Stock video from Pexels API matching scene keywords
3. Stock video from Pixabay API matching scene keywords
4. Custom placeholder video (if placeholder_url is provided)
5. Default placeholder video from environment configuration
6. Raises error if no video source available and use_placeholder is false

## 8. Common Issues

- **Long scripts**: Very long scripts may result in longer processing times. Consider breaking them into smaller segments.
- **Stock media limitations**: Some specific or niche topics may have limited stock media options. Use custom_media or placeholder_url for better control.
- **Voice synthesis quality**: Voice quality may vary depending on the selected voice and language.
- **Queue limitations**: If the maximum queue length is reached, requests may be rejected.
- **Placeholder videos**: Ensure placeholder videos are MP4 format and compatible with the desired aspect ratios.
- **Custom media URLs**: URLs must be directly accessible and return MP4 video content.

## 9. Best Practices

- Keep script paragraphs concise and focused for better scene transitions.
- Test different voices to find the best match for your content.
- Use the webhook_url parameter for long videos to avoid timeouts.
- Review stock media keywords in your script to ensure relevant visuals.
- For time-sensitive content, consider pre-generating videos during off-peak hours.
- Monitor and optimize API usage to avoid queue length limits.
- Prepare high-quality placeholder videos that match your brand style.
- Use custom_media for critical scenes where specific visuals are required.
- Test placeholder videos with different aspect ratios before deployment.
- Consider caching frequently used placeholder videos for better performance.
