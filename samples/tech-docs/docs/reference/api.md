# API Reference

Base URL: `https://api.example.com/v1`

All requests must include an `Authorization: Bearer <token>` header.

## Endpoints

### `GET /ping`

Health check. Returns `200 OK` if the API is reachable.

**Response**

```json
{
  "status": "ok",
  "version": "1.0.0"
}
```

---

### `GET /items`

List all items accessible to the authenticated user.

**Query parameters**

| Parameter | Type    | Required | Description                        |
|-----------|---------|----------|------------------------------------|
| `limit`   | integer | No       | Maximum results to return (max 100)|
| `offset`  | integer | No       | Pagination offset (default 0)      |
| `q`       | string  | No       | Filter by name (substring match)   |

**Response**

```json
{
  "items": [
    { "id": "abc123", "name": "Widget A", "created_at": "2024-01-01T00:00:00Z" },
    { "id": "def456", "name": "Widget B", "created_at": "2024-01-02T00:00:00Z" }
  ],
  "total": 2,
  "limit": 100,
  "offset": 0
}
```

---

### `POST /items`

Create a new item.

**Request body**

```json
{
  "name": "My New Widget",
  "description": "Optional description"
}
```

**Response** — `201 Created`

```json
{
  "id": "ghi789",
  "name": "My New Widget",
  "description": "Optional description",
  "created_at": "2024-03-15T12:00:00Z"
}
```

!!! danger "Rate limits"
    `POST /items` is limited to **10 requests per minute** per token.
    Exceeding this returns `429 Too Many Requests`.

---

### `DELETE /items/{id}`

Delete an item by ID.

**Path parameters**

| Parameter | Type   | Description    |
|-----------|--------|----------------|
| `id`      | string | Item unique ID |

**Response** — `204 No Content`

!!! warning "Irreversible"
    Deletion is permanent. There is no soft-delete or recycle bin.
