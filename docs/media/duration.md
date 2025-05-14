# Media Duration

This endpoint retrieves the duration (in seconds) of a media file (video or audio).

## Endpoint

`POST /v1/media/media-duration`

## Authentication

This endpoint requires API authentication. See [Authentication](../toolkit/authenticate.md) for details.

## Request

```json
{
  "media_url": "https://example.com/media.mp4",
  "webhook_url": "https://example.com/webhook",  // Optional
  "id": "custom-id"  // Optional
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| media_url | string | Yes | URL of the media file to analyze |
| webhook_url | string | No | URL to receive the processing result |
| id | string | No | Custom identifier for tracking the request |

## Response

**Success (200 OK)**

```json
{
  "code": 200,
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "id": "custom-id",
  "response": 87.46,
  "message": "success",
  "run_time": 0.542,
  "queue_time": 0,
  "total_time": 0.542,
  "pid": 12345,
  "queue_id": 67890,
  "queue_length": 0,
  "build_number": "123"
}
```

The `response` field contains the duration in seconds, rounded to 2 decimal places.

**Queued (202 Accepted)**

```json
{
  "code": 202,
  "id": "custom-id",
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "processing",
  "pid": 12345,
  "queue_id": 67890,
  "max_queue_length": "unlimited",
  "queue_length": 0,
  "build_number": "123"
}
```

**Error (4xx/5xx)**

```json
{
  "code": 500,
  "id": "custom-id",
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "Error getting media duration: [error details]",
  "pid": 12345,
  "queue_id": 67890,
  "queue_length": 0,
  "build_number": "123"
}
```

## Example

### Request

```bash
curl -X POST https://api.example.com/v1/media/media-duration \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your_api_key" \
  -d '{
    "media_url": "https://example.com/sample-video.mp4",
    "webhook_url": "https://your-server.com/webhook"
  }'
```

### Response

```json
{
  "code": 200,
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "response": 87.46,
  "message": "success",
  "run_time": 0.542,
  "total_time": 0.542
}