# ShortGPT Video Generation Endpoint (v1)

## 1. Overview

The `/v1/video/shortgpt` endpoint enables powerful video content generation using three different engines from the ShortGPT framework:
- Content Video Engine: Creates videos from scripts with AI-driven editing
- Translation Engine: Translates videos into different languages
- Facts Engine: Generates fact-based short videos automatically

## 2. Configuration

### Required API Keys
- OpenAI API Key (Required): For content generation and text processing
- Pexels API Key (Required): For fetching stock video content
- ElevenLabs API Key (Optional): For premium voice synthesis

### Environment Variables
```bash
# Required API Keys
OPENAI_API_KEY=your_openai_key
PEXELS_API_KEY=your_pexels_key
ELEVENLABS_API_KEY=your_elevenlabs_key  # Optional

# Optional Default Assets
DEFAULT_BACKGROUND_MUSIC=url_to_default_music
DEFAULT_BACKGROUND_VIDEO=url_to_default_video
```

### Docker Run Command
```bash
docker run -p 8080:8080 \
  -e OPENAI_API_KEY=your_openai_key \
  -e PEXELS_API_KEY=your_pexels_key \
  -e ELEVENLABS_API_KEY=your_elevenlabs_key \
  -e DEFAULT_BACKGROUND_MUSIC=your_music_url \
  -e DEFAULT_BACKGROUND_VIDEO=your_video_url \
  no-code-architects-toolkit
```

## 3. Asset Management

The service manages two types of assets:

1. Default Assets:
   - Set through environment variables
   - Persistent across requests
   - Used when no specific assets are provided

2. Request-Specific Assets:
   - Provided in the request body
   - Temporary (cleaned up after use)
   - Override default assets

## 4. Endpoint

**URL:** `/v1/video/shortgpt`
**Method:** `POST`

### Headers

- `x-api-key`: Required. The API key for authentication.

### Common Parameters

These parameters are available for all engine types:

- `engine_type` (string, optional): The type of engine to use. Options:
  - `content` (default): Regular video creation
  - `translation`: Video translation
  - `facts`: Fact-based video generation
- `language` (string, optional): Language code (e.g., 'EN', 'ES', 'DE'). Defaults to 'EN'
- `voice_gender` (string, optional): Either 'male' or 'female'. Defaults to 'male'
- `watermark` (string, optional): Text to display as watermark
- `background_music_url` (string, optional): URL for background music
- `background_video_url` (string, optional): URL for background video

### Engine-Specific Parameters

#### Content Engine (default)
```json
{
    "engine_type": "content",
    "script": "Your video script here",
    "vertical": false,
    "background_music_url": "https://example.com/music.mp3"
}
```

#### Translation Engine
```json
{
    "engine_type": "translation",
    "source_url": "https://youtube.com/watch?v=...",
    "language": "ES",
    "use_captions": true
}
```

#### Facts Engine
```json
{
    "engine_type": "facts",
    "facts_type": "Interesting scientific facts",
    "num_images": 5,
    "background_video_url": "https://example.com/background.mp4",
    "background_music_url": "https://example.com/music.mp3"
}
```

## 5. Response

### Success Response

```json
{
    "status": "success",
    "message": "Video created successfully",
    "video_path": "path/to/generated/video.mp4",
    "steps": [
        "Generating script...",
        "Processing voice synthesis...",
        "Adding background music...",
        "Generating video..."
    ],
    "engine_type": "content"
}
```

### Error Responses

#### Missing API Keys
```json
{
    "status": "error",
    "message": "Missing required API keys: OPENAI_API_KEY, PEXELS_API_KEY"
}
```

#### Invalid Parameters
```json
{
    "status": "error",
    "message": "source_url is required for translation engine"
}
```

## 6. Asset Storage

Assets are stored in two locations:
1. Temporary assets: `/tmp/assets`
2. Persistent assets: `/app/public/assets`

The service automatically manages these directories and cleans up temporary assets after use.

## 7. Best Practices

- Set default background assets for consistent video style
- Use direct URLs for custom assets
- Clean cache periodically if storing many videos
- Monitor API usage for OpenAI and Pexels
- Test different voice combinations
- Use watermarks for branding

## 8. Common Issues

- **API Rate Limits**: Monitor usage of OpenAI and Pexels APIs
- **Asset Access**: Ensure URLs are directly accessible
- **Storage Space**: Monitor disk usage for generated videos
- **Memory Usage**: Large videos may require significant resources
- **Processing Time**: Complex videos take longer to generate
