# S3 Upload Endpoint

The `/v1/s3/upload` endpoint allows you to upload files to S3 storage either from a URL or by directly uploading a file.

## Authentication

Authentication token required in the request header:
```
Authorization: Bearer your-token-here
```

## Endpoint

```
POST /v1/s3/upload
```

## Upload Methods

### 1. URL Upload

Upload a file from a URL by sending a JSON request.

#### Request Body (JSON)

```json
{
    "file_url": "https://example.com/path/to/file.jpg",
    "filename": "custom-name.jpg",  // Optional
    "public": false  // Optional, defaults to false
}
```

#### Parameters

- `file_url` (required): URL of the file to upload
- `filename` (optional): Custom filename for the uploaded file. If not provided, will use the filename from the URL
- `public` (optional): Boolean flag to make the file publicly accessible. Defaults to false

### 2. File Upload

Upload a file directly using multipart form data.

#### Form Data Parameters

- `file` (required): The file to upload
- `filename` (optional): Custom filename for the uploaded file. If not provided, will use the original filename
- `public` (optional): Set to 'true' to make the file publicly accessible. Defaults to false

## Response

### Success Response

```json
{
    "code": 200,
    "job_id": "unique-job-id",
    "response": {
        "file_url": "https://your-s3-bucket.com/filename.ext",
        "filename": "filename.ext",
        "bucket": "your-bucket-name",
        "public": false
    },
    "message": "success"
}
```

### For Queued Jobs

```json
{
    "code": 202,
    "job_id": "unique-job-id",
    "message": "processing"
}
```

### Error Response

```json
{
    "code": 400,
    "message": "Error message here"
}
```

## Examples

### URL Upload Example

```bash
curl -X POST https://api.example.com/v1/s3/upload \
  -H "Authorization: Bearer your-token-here" \
  -H "Content-Type: application/json" \
  -d '{
    "file_url": "https://example.com/image.jpg",
    "filename": "my-image.jpg",
    "public": true
  }'
```

### File Upload Example

```bash
curl -X POST https://api.example.com/v1/s3/upload \
  -H "Authorization: Bearer your-token-here" \
  -F "file=@/path/to/local/file.jpg" \
  -F "filename=my-image.jpg" \
  -F "public=true"
