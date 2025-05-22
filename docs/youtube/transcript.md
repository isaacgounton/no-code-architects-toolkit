# YouTube Transcript API

Get transcripts/subtitles from YouTube videos. This endpoint uses the YouTube Transcript API to fetch subtitles directly from YouTube without requiring an API key or browser automation.

## Features

- Access both manually created and auto-generated subtitles
- Support for multiple languages with fallback options
- Translation capabilities
- HTML formatting preservation option
- Support for age-restricted videos via cookies
- Works with various YouTube URL formats

## API Endpoint

`POST /v1/youtube/transcript`

## Request Body

| Field | Type | Description | Required |
|-------|------|-------------|----------|
| video_url | string | Full YouTube video URL (supports watch, embed, youtu.be formats) | Yes |
| languages | array of strings | List of language codes in order of preference (e.g. ['en', 'es']). Will try each language in order until one is found. Defaults to ['en'] | No |
| preserve_formatting | boolean | Whether to preserve HTML formatting (e.g. `<i>`, `<b>`). Defaults to false | No |
| translate_to | string | Language code to translate transcript to | No |
| cookies_path | string | Path to a netscape-format cookies.txt file for age-restricted videos | No |

### Example Request

```json
{
  "video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
  "languages": ["en", "es"],
  "preserve_formatting": true,
  "translate_to": "fr",
  "cookies_path": "/path/to/cookies.txt"
}
```

## Response

### Success Response

**Code:** 200

**Content:**

```json
{
  "video_id": "dQw4w9WgXcQ",
  "language": {
    "name": "English",
    "code": "en"
  },
  "metadata": {
    "is_generated": false,
    "translation_languages": ["fr", "es", "de", "it"],
    "preserve_formatting": true
  },
  "translated_to": "fr",
  "snippets": [
    {
      "text": "Sample text 1",
      "start": 0.0,
      "duration": 1.54
    },
    {
      "text": "Sample text 2",
      "start": 1.54,
      "duration": 4.16
    }
  ]
}
```

### Error Responses

#### Invalid YouTube URL

**Code:** 400

**Content:**
```json
{
  "error": "Invalid YouTube URL"
}
```

#### No Transcript Available

**Code:** 404

**Content:**
```json
{
  "error": "No transcript available for this video"
}
```

#### Translation Not Available

**Code:** 400

**Content:**
```json
{
  "error": "Selected transcript cannot be translated"
}
```

#### Server Error

**Code:** 500

**Content:**
```json
{
  "error": "Error message details"
}
```

## Cookie Authentication

For age-restricted videos, you'll need to provide a cookies.txt file in Netscape format containing valid YouTube authentication cookies. You can use browser extensions to export cookies:

- Chrome: [Cookie-Editor](https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm) (select "Netscape" format when exporting)
- Firefox: [cookies.txt](https://addons.mozilla.org/en-US/firefox/addon/cookies-txt/)

## Language Codes

Use standard language codes like:
- en (English)
- es (Spanish)
- fr (French)
- de (German)
- it (Italian)
- pt (Portuguese)
etc.

The API will attempt to fetch transcripts in the requested languages in order of preference. If none are available, it will return a 404 error.

## Technical Notes

- The API works without requiring a YouTube API key
- No browser automation is used, making it fast and reliable
- Timestamps are returned in seconds
- Duration indicates how long each snippet is displayed
- Translation uses YouTube's built-in translation feature
- HTML formatting preservation is optional and disabled by default
