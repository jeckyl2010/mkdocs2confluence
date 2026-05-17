## LiteLLM local proxy

Starts the local LiteLLM proxy using Apple Container. The setup uses a pinned non-root LiteLLM image, environment variables from `.env`, and a read-only mounted `litellm_config.yaml`.

### Start container service

Start the Apple Container service if it is not already running:

```bash
container system start
```

Verify status:

```bash
container system status
```

### Start LiteLLM

Start LiteLLM:

```bash
container rm litellm || true

container run \
  --name litellm \
  --memory 4096M \
  --cpus 4 \
  --publish 127.0.0.1:4000:4000 \
  --env-file .env \
  --volume "$PWD/litellm_config.yaml:/app/config.yaml:ro" \
  ghcr.io/berriai/litellm-non_root:1.85.0 \
  --config /app/config.yaml \
  --host 0.0.0.0 \
  --port 4000
```

LiteLLM endpoint:

```text
http://localhost:4000
```

### Validation

Health check:

```bash
curl http://localhost:4000/health \
  -H "Authorization: Bearer <LITELLM_MASTER_KEY>"
```

List configured models:

```bash
curl http://localhost:4000/models \
  -H "Authorization: Bearer <LITELLM_MASTER_KEY>"
```

View container logs:

```bash
container logs litellm
```

List containers:

```bash
container list --all
```