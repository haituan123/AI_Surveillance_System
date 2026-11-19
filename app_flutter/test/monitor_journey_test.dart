import 'dart:convert';
import 'dart:typed_data';

import 'package:app_flutter/core/app_settings.dart';
import 'package:app_flutter/screens/surveillance_screen.dart';
import 'package:app_flutter/services/security_service.dart';
import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  testWidgets('live monitoring starts, updates, exposes zones, and stops', (
    tester,
  ) async {
    var running = false;
    final requestedPaths = <String>[];
    final client = MockClient((request) async {
      requestedPaths.add('${request.method} ${request.url.path}');
      if (request.url.path == '/cameras') {
        return http.Response(jsonEncode([_camera]), 200);
      }
      if (request.url.path == '/zones') {
        return http.Response(jsonEncode([_zone]), 200);
      }
      if (request.url.path == '/surveillance/start') {
        running = true;
        return http.Response(jsonEncode(_status(running: true)), 200);
      }
      if (request.url.path == '/surveillance/stop') {
        running = false;
        return http.Response(jsonEncode(_status(running: false)), 200);
      }
      if (request.url.path == '/surveillance/status') {
        return http.Response(jsonEncode(_status(running: running)), 200);
      }
      if (request.url.path == '/surveillance/latest') {
        return http.Response(jsonEncode(_latest), 200);
      }
      if (request.url.path == '/surveillance/frame') {
        return http.Response('{}', 404);
      }
      return http.Response('{}', 404);
    });

    await _pumpMonitor(tester, SecurityService(client: client));
    expect(find.text('Live monitoring preview'), findsOneWidget);
    expect(find.text('Stopped'), findsWidgets);
    expect(find.text('Restricted zones'), findsOneWidget);
    expect(find.text('Server room'), findsOneWidget);

    await tester.tap(find.text('Start'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    expect(running, isTrue);
    expect(find.text('12.0 FPS'), findsOneWidget);
    expect(find.text('Known Person'), findsOneWidget);
    final zoneField = tester.widget<TextField>(find.byType(TextField).first);
    expect(zoneField.enabled, isTrue);
    expect(find.text('Save 0/4 points'), findsOneWidget);

    await tester.tap(find.text('Stop'));
    await tester.pumpAndSettle();
    expect(running, isFalse);
    expect(find.text('Stopped'), findsWidgets);
    expect(requestedPaths, contains('POST /surveillance/start'));
    expect(requestedPaths, contains('POST /surveillance/stop'));
  });

  testWidgets('quick scan supports cancel, results, threats, and clearing', (
    tester,
  ) async {
    var uploadCount = 0;
    var deleteCount = 0;
    final requestedPaths = <String>[];
    final client = MockClient((request) async {
      requestedPaths.add('${request.method} ${request.url.path}');
      if (request.url.path == '/cameras') {
        return http.Response(jsonEncode([_camera]), 200);
      }
      if (request.url.path == '/zones') {
        return http.Response('[]', 200);
      }
      if (request.url.path == '/surveillance/status') {
        return http.Response(jsonEncode(_status(running: false)), 200);
      }
      if (request.method == 'POST' && request.url.path == '/video-analysis') {
        uploadCount++;
        return http.Response(
          jsonEncode(_videoStatus(completed: uploadCount > 1)),
          200,
        );
      }
      if (request.url.path == '/video-analysis/job-1/status') {
        return http.Response(
          jsonEncode(_videoStatus(completed: uploadCount > 1)),
          200,
        );
      }
      if (request.url.path == '/video-analysis/job-1/results') {
        if (uploadCount == 1) return http.Response('{}', 404);
        return http.Response(jsonEncode(_videoResults), 200);
      }
      if (request.url.path == '/video-analysis/job-1/frame') {
        return http.Response('{}', 404);
      }
      if (request.method == 'DELETE' &&
          request.url.path == '/video-analysis/job-1') {
        deleteCount++;
        return http.Response('{}', 200);
      }
      return http.Response('{}', 404);
    });
    final videoBytes = Uint8List.fromList([1, 2, 3, 4]);

    await _pumpMonitor(
      tester,
      SecurityService(client: client),
      picker: () async => PlatformFile(
        name: 'temporary.mp4',
        size: videoBytes.length,
        bytes: videoBytes,
      ),
    );
    await tester.tap(find.text('Quick video scan'));
    await tester.pump();
    expect(
      find.textContaining('Results are not saved to Activity or history.'),
      findsOneWidget,
    );

    await tester.tap(find.text('Choose video for quick scan'));
    await tester.pump();
    expect(find.text('Cancel quick scan'), findsOneWidget);
    await tester.tap(find.text('Cancel quick scan'));
    await tester.pumpAndSettle();
    expect(deleteCount, 1);
    expect(find.text('No Quick video scan results'), findsOneWidget);

    await tester.tap(find.text('Choose video for quick scan'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.text('1 known'), findsOneWidget);
    expect(find.text('1 unknown'), findsOneWidget);
    expect(find.text('1 threats'), findsOneWidget);
    expect(find.textContaining('knife threat'), findsOneWidget);
    expect(find.text('Clear quick scan result'), findsOneWidget);
    final progress = tester.widget<LinearProgressIndicator>(
      find.byType(LinearProgressIndicator).first,
    );
    expect(progress.value, 1);

    await tester.tap(find.text('Clear quick scan result'));
    await tester.pumpAndSettle();
    expect(deleteCount, 2);
    expect(find.text('No Quick video scan results'), findsOneWidget);
    expect(
      requestedPaths.where((path) => path.contains('/logs')),
      isEmpty,
      reason: 'temporary scans must not write to or query Activity',
    );
  });
}

Future<void> _pumpMonitor(
  WidgetTester tester,
  SecurityService service, {
  QuickScanVideoPicker? picker,
}) async {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = const Size(1280, 720);
  addTearDown(() {
    tester.view.resetPhysicalSize();
    tester.view.resetDevicePixelRatio();
  });
  final settings = AppSettingsController();
  addTearDown(settings.dispose);
  await tester.pumpWidget(
    AppSettingsScope(
      controller: settings,
      child: MaterialApp(
        home: Scaffold(
          body: SurveillanceScreen(
            service: service,
            quickScanVideoPicker: picker,
          ),
        ),
      ),
    ),
  );
  await tester.pump();
  await tester.pump();
}

const _camera = {
  'id': 1,
  'name': 'Laptop webcam',
  'source': '0',
  'location': 'Desk',
  'is_active': true,
  'created_at': '2026-11-19T08:00:00Z',
  'updated_at': '2026-11-19T08:00:00Z',
};

const _zone = {
  'id': 9,
  'camera_id': 1,
  'name': 'Server room',
  'points': [
    {'x': 10, 'y': 10},
    {'x': 100, 'y': 10},
    {'x': 100, 'y': 100},
    {'x': 10, 'y': 100},
  ],
  'is_active': true,
};

Map<String, Object?> _status({required bool running}) => {
      'state': running ? 'running' : 'stopped',
      'running': running,
      'camera_id': 1,
      'session_id': running ? 4 : null,
      'frames_processed': running ? 25 : 0,
      'fps': running ? 12.0 : 0.0,
      'started_at': running ? '2026-11-19T08:00:00Z' : null,
      'error_message': null,
    };

const _latest = {
  'frame_index': 9,
  'width': 640,
  'height': 480,
  'tracks': [
    {
      'track_id': 7,
      'status': 'known',
      'person_confidence': 0.93,
      'bounding_box': {'x1': 10, 'y1': 20, 'x2': 110, 'y2': 180},
      'member_name': 'Known Person',
      'similarity': 0.91,
    },
  ],
};

Map<String, Object?> _videoStatus({required bool completed}) => {
      'job_id': 'job-1',
      'filename': 'temporary.mp4',
      'state': completed ? 'completed' : 'running',
      'persistent': false,
      'processed_frames': completed ? 100 : 10,
      'total_frames': 100,
      'progress': completed ? 1.0 : 0.1,
      'processing_fps': 8.0,
      'error_message': null,
    };

const _videoResults = {
  'job_id': 'job-1',
  'filename': 'temporary.mp4',
  'state': 'completed',
  'persistent': false,
  'summary': {
    'total_frames': 100,
    'duration_seconds': 10.0,
    'average_processing_fps': 8.0,
    'known_events': 1,
    'unknown_events': 1,
    'threat_events': 1,
    'events_truncated': false,
  },
  'events': [
    {
      'event_id': 'event-1',
      'frame_index': 50,
      'timestamp_seconds': 5.0,
      'track_id': null,
      'status': null,
      'member_id': null,
      'member_name': null,
      'similarity': null,
      'event_type': 'knife_threat',
      'detected_label': 'knife',
      'confidence': 0.91,
      'bounding_box': [2, 3, 8, 12],
      'description': 'Person detected holding a knife',
      'is_threat': true,
      'snapshot_url': null,
    },
  ],
};
