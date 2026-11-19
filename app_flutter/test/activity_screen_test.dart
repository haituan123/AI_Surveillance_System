import 'dart:convert';

import 'package:app_flutter/core/app_settings.dart';
import 'package:app_flutter/screens/logs_screen.dart';
import 'package:app_flutter/services/security_service.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  testWidgets('Activity tabs keep filters and record sources separated', (
    tester,
  ) async {
    final client = MockClient((request) async {
      final body = switch (request.url.path) {
        '/logs' => [
            {
              'id': 1,
              'session_id': 1,
              'track_id': 1,
              'status': 'known',
              'member_name': 'Alice',
              'camera_name': 'Front door',
              'confidence': 0.95,
              'detected_at': '2026-11-18T08:00:00',
            },
            {
              'id': 2,
              'session_id': 1,
              'track_id': 2,
              'status': 'unknown',
              'member_name': null,
              'camera_name': 'Loading bay',
              'confidence': 0.85,
              'detected_at': '2026-11-18T08:01:00',
            },
          ],
        '/alerts' => [
            {
              'id': 10,
              'detection_log_id': 2,
              'alert_type': 'unknown_person',
              'message': 'Unknown person detected',
              'camera_name': 'Loading bay',
              'is_read': false,
              'created_at': '2026-11-18T08:01:00',
            },
            {
              'id': 11,
              'detection_log_id': 2,
              'alert_type': 'restricted_area',
              'message': 'Restricted area entered',
              'camera_name': 'Server room',
              'is_read': false,
              'created_at': '2026-11-18T08:02:00',
            },
            {
              'id': 12,
              'detection_log_id': 2,
              'alert_type': 'loitering',
              'message': 'Loitering detected',
              'camera_name': 'Lobby',
              'is_read': true,
              'created_at': '2026-11-18T08:03:00',
            },
          ],
        '/logs/security-events' => [
            {
              'id': 20,
              'source_id': 'video-1',
              'source_type': 'qa_video',
              'source_name': 'warehouse.mp4',
              'event_type': 'weapon_present',
              'start_timestamp': 2,
              'end_timestamp': 4,
              'confidence': 0.91,
              'detected_label': 'knife',
              'status': 'open',
              'created_at': '2026-11-18T08:04:00',
            },
            {
              'id': 21,
              'source_id': 'video-2',
              'source_type': 'qa_video',
              'source_name': 'garage.mp4',
              'event_type': 'fire_smoke',
              'start_timestamp': 5,
              'end_timestamp': 8,
              'confidence': 0.89,
              'detected_label': 'smoke',
              'status': 'open',
              'created_at': '2026-11-18T08:05:00',
            },
          ],
        _ => <Object>[],
      };
      return http.Response(jsonEncode(body), 200);
    });
    final settings = AppSettingsController();
    addTearDown(settings.dispose);
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(1280, 720);
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });

    await tester.pumpWidget(
      AppSettingsScope(
        controller: settings,
        child: MaterialApp(
          home: LogsScreen(service: SecurityService(client: client)),
        ),
      ),
    );
    await tester.pump();
    await tester.pump();

    expect(find.text('Live detections (2)'), findsOneWidget);
    expect(find.byKey(const ValueKey('live-detection-filter-all')),
        findsOneWidget);
    expect(find.byKey(const ValueKey('live-detection-filter-known')),
        findsOneWidget);
    expect(find.byKey(const ValueKey('live-detection-filter-unknown')),
        findsOneWidget);
    expect(find.byKey(const ValueKey('live-alert-filter-unknownPerson')),
        findsNothing);
    expect(find.textContaining('Camera: Front door'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('live-detection-filter-known')));
    await tester.pump();
    expect(find.text('Alice detected'), findsOneWidget);
    expect(find.textContaining('Camera: Loading bay'), findsNothing);
    expect(find.text('1/2 detections'), findsOneWidget);

    await tester.tap(find.text('Live alerts (3)'));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('live-alert-filter-all')), findsOneWidget);
    expect(
      find.byKey(const ValueKey('live-alert-filter-unknownPerson')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey('live-alert-filter-restrictedArea')),
      findsOneWidget,
    );
    expect(find.byKey(const ValueKey('live-alert-filter-loitering')),
        findsOneWidget);
    expect(find.byKey(const ValueKey('live-detection-filter-known')),
        findsNothing);
    expect(find.textContaining('Camera: Loading bay'), findsOneWidget);
    expect(find.text('Mark read'), findsWidgets);
    await tester.tap(
      find.byKey(const ValueKey('live-alert-filter-restrictedArea')),
    );
    await tester.pump();
    expect(find.textContaining('Camera: Server room'), findsOneWidget);
    expect(find.textContaining('Camera: Lobby'), findsNothing);
    expect(find.text('1/3 alerts'), findsOneWidget);

    await tester.tap(find.text('Investigation incidents (2)'));
    await tester.pumpAndSettle();
    expect(
        find.byKey(const ValueKey('investigation-filter-all')), findsOneWidget);
    expect(find.byKey(const ValueKey('investigation-filter-weapons')),
        findsOneWidget);
    expect(
      find.byKey(const ValueKey('investigation-filter-violenceFighting')),
      findsOneWidget,
    );
    expect(find.byKey(const ValueKey('investigation-filter-fireSmoke')),
        findsOneWidget);
    expect(find.byKey(const ValueKey('investigation-filter-theftRobbery')),
        findsOneWidget);
    expect(
      find.text(
        'To remove these incidents, delete their source video in Investigations.',
      ),
      findsOneWidget,
    );
    expect(
      find.textContaining('Investigation video: warehouse.mp4'),
      findsOneWidget,
    );
    expect(find.text('Delete all alerts'), findsNothing);
    await tester.tap(
      find.byKey(const ValueKey('investigation-filter-weapons')),
    );
    await tester.pump();
    expect(
      find.textContaining('Investigation video: warehouse.mp4'),
      findsOneWidget,
    );
    expect(
      find.textContaining('Investigation video: garage.mp4'),
      findsNothing,
    );
    expect(find.text('1/2 incidents'), findsOneWidget);
    expect(tester.takeException(), isNull);

    await tester.pumpWidget(const SizedBox.shrink());
  });
}
