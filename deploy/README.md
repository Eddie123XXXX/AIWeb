# AIWeb Production Deployment

This directory contains a production-ready deployment scaffold for a single Linux server.

## Recommended layout

- `/opt/aiweb/backend`: backend source code and Python virtualenv
- `/opt/aiweb/frontend`: frontend source code
- `/opt/aiweb/deploy`: files from this directory
- `/var/www/aiweb/current`: published frontend static files

## 1. Prepare server packages

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-plugin nginx certbot python3-certbot-nginx python3-venv rsync
sudo systemctl enable --now docker nginx
```

## 2. Start infrastructure

```bash
cd /opt/aiweb
cp deploy/.env.prod.example deploy/.env.prod
$EDITOR deploy/.env.prod
docker compose --env-file deploy/.env.prod -f deploy/docker-compose.prod.yml up -d
```

This production compose intentionally keeps only:

- PostgreSQL
- Redis
- MinIO
- Milvus

It does not expose pgAdmin, RedisInsight, Kibana, Attu, or RabbitMQ by default.

## 3. Configure backend runtime

```bash
cd /opt/aiweb
cp backend/.env.production.example backend/.env.production
$EDITOR backend/.env.production
python3 -m venv backend/.venv
backend/.venv/bin/pip install --upgrade pip
backend/.venv/bin/pip install -r backend/requirements.txt
chmod +x deploy/start-backend.sh deploy/run-schema.sh deploy/publish-frontend.sh
./deploy/run-schema.sh
```

Important backend settings:

- `ALLOWED_ORIGINS` should list your real HTTPS frontend domains.
- `POSTGRES_*`, `REDIS_*`, `MINIO_*`, `MILVUS_*` must point to the local services started by Docker.
- `JWT_SECRET` must be replaced with a strong random secret.
- At least one model key is required for chat. Full feature deployment normally needs `DEEPSEEK_API_KEY` and `QWEN_API_KEY`.

## 4. Install backend service

```bash
sudo cp deploy/aiweb-backend.service /etc/systemd/system/aiweb-backend.service
sudo systemctl daemon-reload
sudo systemctl enable --now aiweb-backend
sudo systemctl status aiweb-backend
```

Logs:

```bash
journalctl -u aiweb-backend -f
```

## 5. Publish frontend

Same-domain deployment is recommended. Leave `VITE_API_BASE` empty in `frontend/.env.production`.

```bash
cd /opt/aiweb
cp frontend/.env.production.example frontend/.env.production
$EDITOR frontend/.env.production
chmod +x deploy/publish-frontend.sh
./deploy/publish-frontend.sh
```

## 6. Configure Nginx and HTTPS

1. Edit `deploy/nginx.aiweb.conf` and replace `ai.example.com` with your real domain.
2. Install the file:

```bash
sudo cp deploy/nginx.aiweb.conf /etc/nginx/sites-available/aiweb.conf
sudo ln -s /etc/nginx/sites-available/aiweb.conf /etc/nginx/sites-enabled/aiweb.conf
sudo nginx -t
sudo systemctl reload nginx
```

3. Issue the certificate:

```bash
sudo certbot --nginx -d ai.example.com -d www.ai.example.com
```

The Nginx config already forwards `/api/` to the backend and supports WebSocket upgrades for chat and Agentic routes.

## 7. Verification checklist

Run these checks after deployment:

- `https://your-domain/` loads the frontend
- `https://your-domain/docs` opens FastAPI Swagger
- registration and login work
- normal chat streams successfully
- conversation history persists after page refresh
- MinIO uploads work
- RAG document processing succeeds
- Milvus-backed retrieval works
- DeepResearch can finish one full session

## 8. Security and operations

- Do not reuse the development `.env` values from your current machine.
- Keep database, Redis, MinIO, and Milvus bound to `127.0.0.1` unless you have a private network reason not to.
- Back up Docker volumes and the backend `.env.production` file.
- Do not publish MinIO console, pgAdmin, RedisInsight, or similar panels to the public internet.
- Rotate any API keys that have already been used in local testing or shared screenshots.
- Add a host firewall such as UFW and only allow `22`, `80`, and `443`.

Example UFW commands:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

Example backup commands:

```bash
mkdir -p /opt/backup/aiweb
docker run --rm -v aiweb_postgres_data:/from -v /opt/backup/aiweb:/to alpine sh -c "cd /from && tar czf /to/postgres-data.tgz ."
docker run --rm -v aiweb_minio_data:/from -v /opt/backup/aiweb:/to alpine sh -c "cd /from && tar czf /to/minio-data.tgz ."
cp /opt/aiweb/backend/.env.production /opt/backup/aiweb/backend.env.production
```
