# How to Structure Prompts for the Best Video Results

Here's how to organize your prompts for optimal video variety and quality:

## Basic Structure Guidelines

1. **Use Clear Paragraph Breaks**: Separate major sections with double line breaks (`\n\n`) to create distinct scenes.

2. **Keep Scene Content Visual**: Include descriptive, visual language that can be matched with relevant videos.

3. **Optimal Scene Length**: Aim for 2-3 lines per scene for best results (the system will now split longer paragraphs).

4. **Use Custom Media Strategically**: Specify custom videos for critical scenes where stock footage won't work.

## Example Prompts

### Example 1: Product Showcase

```json
{
  "script": "Introducing the new XYZ Fitness Tracker.\n\nTrack your steps with precision accuracy throughout your day.\n\nMonitor your heart rate during intense workouts.\n\nAnalyze your sleep patterns for better rest.\n\nSync with your smartphone for instant updates.\n\nThe sleek design fits comfortably on any wrist.\n\nWaterproof up to 50 meters for swimming and diving.\n\nAvailable in five stunning colors.\n\nXYZ Fitness Tracker - Your health journey starts here.",
  "aspect_ratio": "9:16",
  "custom_media": [
    {
      "scene_index": 0,
      "media_url": "https://example.com/product-hero.mp4" 
    },
    {
      "scene_index": 8,
      "media_url": "https://example.com/product-closing.mp4"
    }
  ]
}
```

### Example 2: Educational Content

```json
{
  "script": "The Water Cycle: Earth's Recycling System\n\nWater evaporates from oceans, lakes, and rivers due to the sun's heat.\n\nThe invisible water vapor rises into the atmosphere.\n\nAs it rises, the vapor cools and condenses into tiny water droplets.\n\nThese droplets form clouds that move across the sky.\n\nWhen the droplets become too heavy, they fall as precipitation.\n\nRain, snow, and hail return water to the Earth's surface.\n\nSome water flows into streams, rivers, and eventually back to the ocean.\n\nOther water seeps into the ground, becoming groundwater.\n\nPlants absorb water through their roots and release it through transpiration.\n\nThe cycle continues endlessly, purifying and distributing water globally.",
  "voice": "en-US-GuyNeural",
  "aspect_ratio": "16:9",
  "add_captions": true
}
```

### Example 3: Social Media Tips (Short-Form)

```json
{
  "script": "5 Instagram Growth Hacks for 2025\n\nPost consistently at peak engagement times for your audience.\n\nUse trending audio to boost your content in the algorithm.\n\nCreate carousel posts that encourage multiple interactions.\n\nRespond to comments within the first hour to increase engagement.\n\nCollaborate with creators in your niche to reach new audiences.",
  "aspect_ratio": "9:16",
  "voice": "en-US-JennyNeural",
  "add_captions": true
}
```

### Example 4: Recipe/Cooking

```json
{
  "script": "How to Make Perfect Chocolate Chip Cookies\n\nPreheat your oven to 375°F and line a baking sheet with parchment paper.\n\nCream together butter and both white and brown sugars until light and fluffy.\n\nAdd eggs and vanilla extract, mixing until well combined.\n\nIn a separate bowl, whisk together flour, baking soda, and salt.\n\nGradually add the dry ingredients to the wet ingredients.\n\nFold in chocolate chips and nuts if desired.\n\nScoop tablespoon-sized portions onto your baking sheet.\n\nBake for 9-11 minutes until edges are golden but centers are soft.\n\nLet cool for 5 minutes before transferring to a wire rack.\n\nStore in an airtight container and enjoy within 5 days.",
  "voice": "en-US-AriaNeural",
  "aspect_ratio": "1:1",
  "add_captions": true
}
```

## Pro Tips

1. **Descriptive Language**: Include visually descriptive terms that will help find relevant stock footage.

2. **Scene Pacing**: Keep each paragraph focused on one visual concept for better video matching.

3. **Balanced Length**: The system now processes 2-3 lines at a time for longer paragraphs, so distribute your content accordingly.

4. **Strategic Keywords**: Include industry-specific terms that might match available stock footage.

5. **Custom Video Planning**: For scene indices, remember the first scene is index 0, and with the new splitting logic, your scenes may be more numerous than paragraphs.

## Available Voices

Some common voice options include:
- `en-US-AriaNeural` (Female)
- `en-US-GuyNeural` (Male)
- `en-US-JennyNeural` (Female)
- `en-GB-SoniaNeural` (British Female)
- `en-AU-NatashaNeural` (Australian Female)

## Aspect Ratio Options

- `16:9` - Standard landscape (horizontal) video
- `9:16` - Vertical video for stories/reels/TikTok
- `1:1` - Square format for Instagram and Facebook feeds

## Webhook Usage

Add a `webhook_url` parameter to process longer videos in the background:

```json
{
  "script": "Your script here...",
  "webhook_url": "https://your-callback-url.com/webhook"
}
``` 