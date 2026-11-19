import 'package:app_flutter/core/app_settings.dart';
import 'package:app_flutter/screens/dashboard_screen.dart';
import 'package:app_flutter/services/member_service.dart';
import 'package:app_flutter/services/security_service.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  testWidgets('empty Overview shows compact quick actions and first-use steps',
      (
    tester,
  ) async {
    final client = MockClient((request) async {
      return switch (request.url.path) {
        '/health' => http.Response('{}', 200),
        '/members' => http.Response('[]', 200),
        '/surveillance/status' => http.Response(
            '{"state":"stopped","running":false,"frames_processed":0,"fps":0}',
            200,
          ),
        '/alerts' => http.Response('[]', 200),
        '/logs' => http.Response('[]', 200),
        _ => http.Response('Not found', 404),
      };
    });
    final settings = AppSettingsController();
    addTearDown(settings.dispose);

    var registerCount = 0;
    var liveCount = 0;
    var scanCount = 0;
    var investigationCount = 0;
    var activityCount = 0;

    await tester.pumpWidget(
      AppSettingsScope(
        controller: settings,
        child: MaterialApp(
          home: DashboardScreen(
            securityService: SecurityService(client: client),
            memberService: MemberService(client: client),
            onRegisterPerson: () => registerCount++,
            onStartSurveillance: () => liveCount++,
            onQuickVideoScan: () => scanCount++,
            onStartInvestigation: () => investigationCount++,
            onViewLogs: () => activityCount++,
          ),
        ),
      ),
    );
    await tester.pump();
    await tester.pump();

    expect(find.text('Quick actions'), findsOneWidget);
    expect(find.text('Register a person'), findsOneWidget);
    expect(find.text('Start live monitoring'), findsOneWidget);
    expect(find.text('Run a quick video scan'), findsOneWidget);
    expect(find.text('Start a video investigation'), findsOneWidget);
    expect(find.text('View activity'), findsWidgets);
    expect(find.text('Get started in three steps'), findsOneWidget);
    expect(find.text('Register people.'), findsOneWidget);
    expect(
      find.text('Start live monitoring or scan a video.'),
      findsOneWidget,
    );
    expect(
      find.text('Review Activity or investigate footage.'),
      findsOneWidget,
    );

    for (final action in <(String, VoidCallback)>[
      ('overview-register-action', () => expect(registerCount, 1)),
      ('overview-live-monitoring-action', () => expect(liveCount, 1)),
      ('overview-quick-scan-action', () => expect(scanCount, 1)),
      ('overview-investigation-action', () => expect(investigationCount, 1)),
      ('overview-activity-action', () => expect(activityCount, 1)),
    ]) {
      final finder = find.byKey(ValueKey(action.$1));
      await tester.ensureVisible(finder);
      await tester.tap(finder);
      action.$2();
    }

    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox.shrink());
  });
}
