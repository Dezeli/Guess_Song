# Guess Song

차트 기반 자동 음악 퀴즈 서비스.

## Stack

- Backend: Django, Django Ninja, Channels, Celery
- Frontend: React, Vite, TypeScript, Zustand
- Data: PostgreSQL, Redis
- Runtime: Docker Compose, Nginx

## Structure

```text
backend/
  apps/
    core/
    catalog/
    ingestion/
    moderation/
    quizzes/
    rooms/
  config/

frontend/
  src/

nginx/
docker-compose.yml
docker-compose.prod.yml
```

## Local Development

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Then open:

- Frontend through Nginx: http://localhost
- Backend health check: http://localhost/api/health
- Django admin: http://localhost/admin

## Backend Apps

- `core`: common base models, utilities, exceptions, health check
- `catalog`: artists, tracks, albums, charts, external IDs, YouTube candidates
- `ingestion`: chart collection, metadata enrichment, YouTube search, scoring jobs
- `moderation`: review actions and approval/rejection history
- `quizzes`: questions, answer aliases, difficulty, quiz packs
- `rooms`: rooms, participants, game sessions, rounds, submissions, WebSocket flow
