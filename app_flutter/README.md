# AI Face Security Flutter App

Flutter UI for the AI Face Recognition Security System.

## Backend integration

Run the FastAPI backend at `http://127.0.0.1:8000`, or override it when
starting Flutter:

```powershell
flutter run -d windows --dart-define=BACKEND_URL=http://127.0.0.1:8000
```

The Surveillance page supports two mutually exclusive modes:

- **Live webcam** uses a configured camera (the **Add laptop webcam** button
  creates source `0`). Live sessions save meaningful detection logs, confirmed
  unknown-person alerts, and alert snapshots through the backend.
- **Upload video** sends a local video for temporary background analysis.
  Progress, annotated frames, and events are polled while the job exists, but
  none of those results are written to persistent history.

The Dashboard and Logs pages show persistent live-mode data only. This makes it
clear that uploaded-video results are presentation-time results rather than
surveillance records.

The **Video Q&A** page maintains separate conversations, uploads and indexes
footage, and displays answers with supporting frame evidence. Answer generation
requires `GEMINI_API_KEY` in the backend environment.

See the root `README.md` for full Windows/macOS setup, backend setup, model
download, and run instructions.

Quick run after the backend is already running:

```bash
flutter pub get
flutter run -d windows
```

On macOS:

```bash
flutter pub get
flutter run -d macos
```
