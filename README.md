# AI Face Recognition Security System

AI-assisted surveillance application with a Flutter interface and FastAPI
backend. It can register known faces, monitor a camera, analyze uploaded video,
raise security alerts, and answer questions about indexed surveillance footage.

## Features

- Register and manage known people from face images.
- Detect and track people with YOLOv8 and ByteTrack.
- Match faces against the known-person gallery with InsightFace.
- Monitor a configured webcam and save meaningful logs, alerts, and snapshots.
- Define restricted zones and alert when an unknown person lingers inside one.
- Analyze uploaded videos without adding them to live-surveillance history.
- Index video evidence and use Gemini for multilingual Video Q&A.

Only one heavy analysis pipeline can run at a time. Live surveillance and the
temporary uploaded-video analyzer are therefore mutually exclusive.

## Method 1: run the web app with Docker

Requirements: Git and Docker Desktop with Docker Compose.

```powershell
git clone <repository-url>
cd AI_Surveillance_System
Copy-Item .env.example .env
docker compose up --build
```

Open the web application at <http://localhost:8080>. The backend API and its
interactive documentation are available at <http://localhost:8000/health/readiness>
and <http://localhost:8000/docs>.

The Video Q&A feature needs a Gemini API key. Put it in the root `.env` file
before starting Docker:

```dotenv
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-3.6-flash
GEMINI_FALLBACK_MODEL=gemini-3.1-flash-lite
GEMINI_TIMEOUT_SECONDS=60
```

Video Q&A tries the primary model first, then the fallback model when the
primary model is temporarily unavailable. The longer timeout prevents normal
Gemini responses from being abandoned prematurely.

Face recognition and video analysis work without that key. The first AI request
may be slow while the YOLO and InsightFace assets are downloaded into the
persistent model volume.

Useful Docker commands:

```powershell
docker compose ps
docker compose logs -f backend
docker compose down
docker compose up --build -d
```

The following named volumes survive normal container restarts:

- `backend_database`: SQLite database
- `backend_data`: registered images, snapshots, and runtime files
- `backend_models`: downloaded AI models

Running `docker compose down -v` deliberately deletes all three volumes and
their saved application data.

### Webcam note

Docker Desktop may not expose the host webcam to a Linux container. Uploaded
video works normally in Docker. For reliable laptop-webcam access, use the local
Windows or macOS setup below.

## Method 2: run the native app locally

Requirements:

- Python 3.12
- Flutter SDK compatible with Dart 3.11 or newer
- Git
- Windows desktop: Visual Studio with Desktop development tools
- macOS desktop: Xcode

### Windows

This method runs FastAPI from a project-local Python environment and Flutter as
a native Windows desktop application. It is the recommended method when laptop
webcam access is required.

Requirements:

- 64-bit Python 3.12 (the `py` launcher or `python` must be on `PATH`)
- Flutter with Dart 3.11 or newer
- Visual Studio 2022 with **Desktop development with C++** and a Windows SDK

From PowerShell in the repository root, perform the one-time setup:

```powershell
.\scripts\setup.ps1
```

The script creates `.venv`, installs the Python and Flutter dependencies, and
creates `backend\.env` from the committed example when needed. It also checks
that Flutter can see the Visual Studio Windows desktop toolchain.

For Video Q&A, put the Gemini key in the local backend configuration before
starting the application:

```dotenv
# backend/.env
GEMINI_API_KEY=your_key_here
```

Start the complete local application with one command:

```powershell
.\scripts\start_windows.ps1
```

This starts the backend in the background, waits until it is ready, and then
runs Flutter on Windows. When Flutter exits, the backend process started by the
script is stopped automatically. Backend startup logs are written to
`backend\backend_server.out.log` and `backend\backend_server.err.log`.

Alternatively, run the two components in separate terminals. In the first
terminal:

```powershell
.\scripts\start_backend.ps1
```

In the second terminal:

```powershell
.\scripts\start_flutter.ps1
```

The local Windows backend stores its database, uploaded files, and downloaded
models under `backend\`. Docker uses separate named volumes, so Docker and local
mode do not share runtime data by default.

### macOS or Linux

```bash
bash scripts/setup.sh
bash scripts/start_backend.sh
```

In a second terminal, start Flutter (the default target is macOS):

```bash
bash scripts/start_flutter.sh
```

Override the target with `FLUTTER_DEVICE` and the API location with
`BACKEND_URL` when needed.

The Flutter desktop application is intended for Windows and macOS. On Linux,
the Docker-served Flutter web application is the simplest supported UI.

## First use

1. Register one or more known people from clear, single-face images.
2. Open **Surveillance**.
3. Choose **Live webcam**, add the laptop webcam if necessary, and start it; or
   choose **Upload video** for temporary analysis.
4. Review saved live events in **Logs & Alerts**.
5. Open **Video Q&A** to upload/index footage and ask questions about it.

Uploaded-video analyzer results are temporary and do not appear in persistent
live-surveillance history. Video Q&A has its own conversations and indexed
evidence stored in SQLite.

## Configuration

- Local backend settings: `backend/.env` (copy of `backend/.env.example`)
- Docker host ports and Gemini credentials: root `.env` (copy of `.env.example`)
- Docker backend defaults: `docker/backend.env`
- Flutter backend URL: `--dart-define=BACKEND_URL=http://HOST:PORT`

Do not commit either real `.env` file. Both are ignored by Git and excluded from
the Docker build context.

## Verification

After local setup:

```powershell
.\scripts\verify_project.ps1
```

This runs the backend unit tests, Flutter static analysis, and Flutter tests.

To validate the Docker Compose file without starting containers:

```powershell
docker compose config -q
```

## Project layout

```text
backend/       FastAPI API, SQLite services, AI pipeline, and tests
app_flutter/   Flutter desktop/web interface
docker/        Container environment and Nginx reverse proxy
scripts/       Setup, startup, verification, and smoke-test helpers
docs/          Project documents
```

## Troubleshooting

- Backend unavailable: open `/health/readiness` and inspect the returned checks.
- First AI request is slow: wait for the model download and initialization.
- Camera cannot open: close other apps using it and run the backend locally.
- HTTP 409 when starting analysis: stop the other active analysis mode first.
- Video Q&A cannot generate an answer: set `GEMINI_API_KEY` and restart the backend.
- Port already in use: change `BACKEND_PORT` or `FRONTEND_PORT` in the root `.env`.
