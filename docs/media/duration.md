# Media Duration API Documentation

## Overview
The Media Duration endpoint is part of the v1 API suite, providing duration information for audio and video files. This endpoint supports both direct response and queued processing with webhook support for asynchronous operations.

## Endpoint
- **URL**: `/v1/media/media-duration`
- **Method**: `POST`
- **Blueprint**: `v1_media_duration_bp`

## Request

### Headers
- `x-api-key`: Required. Authentication key for API access.
- `Content-Type`: Required. Must be `application/json`.

### Body Parameters

#### Required Parameters
- `media_url` (string)
  - Format: URI
  - Description: URL of the media file to analyze

#### Optional Parameters
- `webhook_url` (string)
  - Format: URI
  - Description: URL to receive the duration results asynchronously
  
- `id` (string)
  - Description: Custom identifier for the duration request

### Example Request

```bash
curl -X POST "https://api.example.com/v1/media/media-duration" \
  -H "x-api-key: your_api_key" \
  -H "Content-Type: application/json" \
  -d '{
    "media_url": "https://example.com/media/file.mp4",
    "webhook_url": "https://your-webhook.com/callback",
    "id": "custom-job-123"
  }'
```

## Response

### Immediate Response (200 OK)
When processed directly (no webhook):

```json
{
  "code": 200,
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "id": "custom-job-123",
  "response": 87.46,
  "message": "success",
  "pid": 12345,
  "queue_id": 67890,
  "run_time": 0.542,
  "queue_time": 0,
  "total_time": 0.542,
  "queue_length": 0,
  "build_number": "1.0.0"
}
```

### Queued Response (202 Accepted)
When a webhook URL is provided:

```json
{
  "code": 202,
  "id": "custom-job-123",
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "processing",
  "pid": 12345,
  "queue_id": 67890,
  "max_queue_length": "unlimited",
  "queue_length": 1,
  "build_number": "1.0.0"
}
```

### Success Response (via Webhook)
```json
{
  "endpoint": "/v1/media/media-duration",
  "code": 200,
  "id": "custom-job-123",
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "response": 87.46,
  "message": "success",
  "pid": 12345,
  "queue_id": 67890,
  "run_time": 0.542,
  "queue_time": 0.123,
  "total_time": 0.665,
  "queue_length": 0,
  "build_number": "1.0.0"
}
```

### Error Responses

#### Queue Full (429 Too Many Requests)
```json
{
  "code": 429,
  "id": "custom-job-123",
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "MAX_QUEUE_LENGTH (100) reached",
  "pid": 12345,
  "queue_id": 67890,
  "queue_length": 100,
  "build_number": "1.0.0"
}
```

#### Server Error (500 Internal Server Error)
```json
{
  "endpoint": "/v1/media/media-duration",
  "code": 500,
  "id": "custom-job-123",
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "response": null,
  "message": "Error getting media duration: [error details]",
  "pid": 12345,
  "queue_id": 67890,
  "run_time": 0.123,
  "queue_time": 0.056,
  "total_time": 0.179,
  "queue_length": 1,
  "build_number": "1.0.0"
}
```

## Error Handling

### Common Errors
- **Invalid API Key**: 401 Unauthorized
- **Invalid JSON Payload**: 400 Bad Request
- **Missing Required Fields**: 400 Bad Request
- **Invalid media_url**: 400 Bad Request
- **Queue Full**: 429 Too Many Requests
- **Processing Error**: 500 Internal Server Error

### Validation Errors
The endpoint performs strict validation of the request payload using JSON Schema. Common validation errors include:
- Invalid URI format for media_url or webhook_url
- Unknown properties in the request body
- Missing required media_url parameter

## Usage Notes

1. **Processing Modes**
   - Direct processing when no webhook_url is provided
   - Asynchronous processing with webhook notification when webhook_url is provided

2. **Queue Management**
   - Requests with webhook_url are queued for processing
   - MAX_QUEUE_LENGTH environment variable controls queue size
   - Set MAX_QUEUE_LENGTH to 0 for unlimited queue size

3. **Duration Format**
   - Duration is returned in seconds
   - Values are rounded to 2 decimal places
   - Supports both audio and video files

## Common Issues

1. **Media Access**
   - Ensure media_url is publicly accessible
   - Verify media file format is supported
   - Check for media file corruption

2. **Webhook Delivery**
   - Ensure webhook_url is publicly accessible
   - Implement webhook endpoint retry logic
   - Monitor webhook endpoint availability

3. **Resource Usage**
   - Large media files may take longer to process
   - Monitor queue length for production deployments
   - Consider implementing request size limits

## Best Practices

1. **Request Handling**
   - Always provide a unique id for job tracking
   - Implement webhook retry logic
   - Store job_id for result correlation

2. **Resource Management**
   - Monitor queue length in production
   - Implement appropriate timeout handling
   - Use direct processing for small files

3. **Error Handling**
   - Implement comprehensive webhook error handling
   - Log job_id with all related operations
   - Monitor processing times and error rates

4. **Security**
   - Use HTTPS for media_url and webhook_url
   - Implement webhook authentication
   - Validate media file types before processing

## N8n Integration

When using this endpoint in n8n's HTTP Request node:

1. Method: POST
2. URL: Your API endpoint
3. Authentication: Header Auth with x-api-key
4. Request Body:
```json
{
  "media_url": "https://example.com/media.mp4"
}
```

Note: Add parameters directly to the request body, not nested under "bodyParameters".
