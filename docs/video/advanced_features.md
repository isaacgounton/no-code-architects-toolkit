# Advanced Video Generation Features

## 1. Content Translation

The `/v1/video/translate` endpoint allows you to translate and dub videos into different languages while maintaining high quality and synchronization.

### Example Request
```json
{
    "video_url": "https://example.com/video.mp4",
    "target_language": "es",
    "voice": "es-ES-ElviraNeural",
    "add_captions": true,
    "subtitle_style": "overlay"  // original/overlay/dual
}
```

## 2. Background Music

Add automatic background music to your videos by specifying the mood and volume in your request:

```json
{
    "script": "Your script here",
    "tts": "edge-tts",
    "voice": "en-US-AriaNeural",
    "background_music": {
        "mood": "upbeat",  // upbeat, calm, dramatic, suspense
        "volume": 0.2,     // 0.0 to 1.0
        "fade": true       // Enable fade in/out
    }
}
```

## 3. Visual Style Presets

Apply predefined visual styles to your videos for consistent branding and professional looks:

```json
{
    "script": "Your script here",
    "style_preset": "educational",  // educational, vlog, news, social-story
    "visual_effects": {
        "transitions": "fade",      // fade, slide, zoom
        "color_grade": "vivid",     // vivid, cinematic, muted
        "overlay_effects": {
            "enabled": true,
            "style": "minimal"      // minimal, dynamic, branded
        }
    }
}
```

## 4. Auto B-Roll Generation

Automatically generate and insert relevant B-roll footage based on your script content:

```json
{
    "script": "Your script here",
    "b_roll": {
        "enabled": true,
        "style": "illustrative",     // illustrative, abstract, literal
        "timing": "auto",            // auto, manual
        "source_priority": [
            "custom",                // Your custom footage first
            "stock",                // Stock footage second
            "generated"             // AI-generated content last
        ]
    }
}
```

## 5. Scene Timing and Pacing

Control the pacing and timing of your video scenes:

```json
{
    "script": "Your script here",
    "timing": {
        "pace": "dynamic",           // dynamic, steady, custom
        "scene_duration": {
            "min": 2.5,             // Minimum scene duration in seconds
            "max": 8.0              // Maximum scene duration in seconds
        },
        "transition_duration": 0.5   // Transition duration in seconds
    }
}
```

## Best Practices

1. **Content Translation**
   - Provide context notes for better translation accuracy
   - Test voice selection for natural-sounding results
   - Consider cultural adaptations when necessary

2. **Background Music**
   - Use lower volumes (0.1-0.3) for background music under voice
   - Match music mood to content theme
   - Enable fading for smooth transitions

3. **Visual Styles**
   - Test presets with your typical content
   - Maintain consistent styling across video series
   - Custom-tune presets for your brand

4. **B-Roll**
   - Provide detailed scripts for better matching
   - Use custom footage for brand-specific elements
   - Review and cache frequently used B-roll

5. **Timing and Pacing**
   - Consider content type when setting pace
   - Use dynamic pacing for engaging content
   - Keep minimum durations readable
