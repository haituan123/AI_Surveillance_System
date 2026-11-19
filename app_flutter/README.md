# AI Face Security Flutter App

Flutter UI for the AI Face Recognition Security System.

## Backend integration

Run the FastAPI backend at `http://127.0.0.1:8000`, or override it when
starting Flutter:

```powershell
flutter run -d windows --dart-define=BACKEND_URL=http://127.0.0.1:8000
```

The **Monitor** page supports two mutually exclusive modes:

- **Live monitoring** uses a configured camera (the **Add laptop webcam** button
  creates source `0`). Live sessions save meaningful detection logs, confirmed
  unknown-person alerts, and alert snapshots through the backend.
- **Quick video scan** sends one local video for temporary background analysis.
  Progress, annotated frames, and events are polled while the job exists, but
  none of those results are written to Activity or persistent history.

**Overview** summarizes the system. **Activity** separates persistent Live
monitoring detections and alerts from indexed Investigation incidents.

The **Investigations** page maintains separate conversations, uploads and
indexes footage, and displays answers with supporting frame evidence. Answer
generation requires `GEMINI_API_KEY` in the backend environment.

See the root `README.md` for full Windows/macOS setup, backend setup, model
download, and run instructions.

On Windows, the root project provides a one-command native launcher after
running `scripts\setup.ps1` once:

```powershell
.\scripts\start_windows.ps1
```

Quick run from this directory after the backend is already running:

```powershell
flutter pub get
flutter run -d windows --dart-define=BACKEND_URL=http://127.0.0.1:8000
```

On macOS:

```bash
flutter pub get
flutter run -d macos --dart-define=BACKEND_URL=http://127.0.0.1:8000
```
