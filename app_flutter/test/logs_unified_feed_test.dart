import 'package:app_flutter/core/app_settings.dart';
import 'package:app_flutter/screens/logs_screen.dart';
import 'package:app_flutter/services/security_service.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  testWidgets(
    'logs screen combines detections alerts and uploaded video events by time',
    (tester) async {
      final client = MockClient((request) async {
        switch (request.url.path) {
          case '/logs':
            return http.Response(
              '[{"id":1,"session_id":3,"track_id":2,'
              '"status":"known","member_name":"Alice",'
              '"camera_name":"Front door","confidence":0.94,'
              '"detected_at":"2026-11-19T08:00:00Z"}]',
              200,
            );
          case '/alerts':
            return http.Response(
              '[{"id":2,"detection_log_id":1,'
              '"alert_type":"restricted_area",'
              '"message":"Unknown person entered Lobby",'
              '"camera_name":"Lobby camera","is_read":false,'
              '"created_at":"2026-11-19T08:01:00Z",'
              '"snapshot_url":null}]',
              200,
            );
          case '/logs/security-events':
            return http.Response(
              '[{"id":3,"source_id":"qa-fight",'
              '"source_type":"qa_video","source_name":"fight.mp4",'
              '"camera_name":null,"event_type":"fighting",'
              '"start_timestamp":2.5,"end_timestamp":4.0,'
              '"confidence":0.87,"detected_label":"person",'
              '"actor_track_ids":[3,8],"status":"open",'
              '"created_at":"2026-11-19T08:02:00Z"}]',
              200,
            );
        }
        return http.Response('Not found', 404);
      });
      final settings = AppSettingsController();
      addTearDown(settings.dispose);
      final service = SecurityService(
        client: client,
        baseUrl: 'http://backend.test',
      );

      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = const Size(1200, 900);
      addTearDown(() {
        tester.view.resetDevicePixelRatio();
        tester.view.resetPhysicalSize();
      });

      await tester.pumpWidget(
        AppSettingsScope(
          controller: settings,
          child: MaterialApp(home: LogsScreen(service: service)),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byType(TabBar), findsNothing);
      expect(find.text('DETECTION LOG'), findsOneWidget);
      expect(find.text('ALERT'), findsOneWidget);
      expect(find.text('UPLOADED VIDEO EVENT'), findsOneWidget);
      expect(find.textContaining('fight.mp4'), findsOneWidget);

      final videoTop = tester.getTopLeft(find.text('UPLOADED VIDEO EVENT')).dy;
      final alertTop = tester.getTopLeft(find.text('ALERT')).dy;
      final detectionTop = tester.getTopLeft(find.text('DETECTION LOG')).dy;
      expect(videoTop, lessThan(alertTop));
      expect(alertTop, lessThan(detectionTop));

      await tester.pumpWidget(const SizedBox.shrink());
    },
  );
}
