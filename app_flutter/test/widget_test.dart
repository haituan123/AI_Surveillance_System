import 'package:app_flutter/app.dart';
import 'package:app_flutter/theme/app_tokens.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  final viewports = <String, Size>{
    'desktop': const Size(1440, 900),
    'tablet': const Size(900, 700),
    'mobile': const Size(390, 844),
  };

  for (final entry in viewports.entries) {
    testWidgets('renders main shell at ${entry.key} size', (tester) async {
      SharedPreferences.setMockInitialValues({});
      await _setViewport(tester, entry.value);
      await tester.pumpWidget(const FaceSecurityApp());
      await tester.pump();
      expect(tester.takeException(), isNull, reason: 'dashboard overflow');

      expect(find.text('Overview'), findsWidgets);
      expect(find.text('People'), findsWidgets);
      expect(find.text('Monitor'), findsWidgets);
      expect(find.text('Investigations'), findsWidgets);
      expect(find.text('Activity'), findsWidgets);

      await _tapDestination(tester, Icons.people_alt_outlined);
      expect(find.text('Registered people'), findsWidgets);
      expect(find.text('Register a person'), findsOneWidget);
      await tester.tap(find.text('Register a person'));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull, reason: 'register overflow');
      expect(find.text('Person details'), findsOneWidget);
      expect(find.text('No images selected'), findsOneWidget);

      await _tapDestination(tester, Icons.videocam_outlined);
      expect(tester.takeException(), isNull, reason: 'surveillance overflow');
      expect(find.text('Monitor'), findsWidgets);
      expect(find.text('Live monitoring'), findsOneWidget);
      expect(find.text('Quick video scan'), findsOneWidget);
      expect(find.text('Live monitoring preview'), findsOneWidget);

      await _tapDestination(tester, Icons.receipt_long_outlined);
      expect(tester.takeException(), isNull, reason: 'logs overflow');
      expect(find.text('Activity'), findsWidgets);
      expect(
        find.textContaining(
          entry.value.width < AppBreakpoints.compact
              ? 'Detections'
              : 'Live detections',
        ),
        findsWidgets,
      );
    });
  }

  testWidgets('settings switch language and theme', (tester) async {
    SharedPreferences.setMockInitialValues({});
    await _setViewport(tester, const Size(1440, 900));
    await tester.pumpWidget(const FaceSecurityApp());
    await tester.pumpAndSettle();

    await tester.tap(find.byIcon(Icons.settings_outlined).first);
    await tester.pumpAndSettle();
    expect(find.text('Settings'), findsWidgets);

    await tester.tap(find.text('Vietnamese'));
    await tester.pumpAndSettle();
    expect(find.text('Cài đặt'), findsWidgets);
    expect(find.text('Tổng quan'), findsWidgets);
    expect(find.text('Mọi người'), findsOneWidget);
    expect(find.text('Theo dõi'), findsOneWidget);
    expect(find.text('Điều tra'), findsOneWidget);
    expect(find.text('Hoạt động'), findsOneWidget);

    await tester.tap(find.text('Tối'));
    await tester.pumpAndSettle();
    final app = tester.widget<MaterialApp>(find.byType(MaterialApp));
    expect(app.themeMode, ThemeMode.dark);
  });

  testWidgets(
    'Overview quick actions open the correct destinations and modes',
    (tester) async {
      SharedPreferences.setMockInitialValues({'app_language': 'en'});
      await _setViewport(tester, const Size(1440, 900));
      await tester.pumpWidget(const FaceSecurityApp());
      await tester.pump();

      Future<void> tapAction(String key) async {
        final action = find.byKey(ValueKey(key));
        await tester.ensureVisible(action);
        await tester.tap(action);
        await tester.pumpAndSettle();
      }

      Future<void> returnToOverview() async {
        await _tapDestination(tester, Icons.dashboard_outlined);
        await tester.pump();
      }

      await tapAction('overview-register-action');
      expect(find.text('Person details'), findsOneWidget);
      await returnToOverview();

      await _tapDestination(tester, Icons.people_alt_outlined);
      await tester.pumpAndSettle();
      expect(find.text('Registered people'), findsWidgets);
      expect(find.text('Person details'), findsNothing);
      await returnToOverview();

      await tapAction('overview-live-monitoring-action');
      expect(find.text('Live monitoring preview'), findsOneWidget);
      await returnToOverview();

      await tapAction('overview-quick-scan-action');
      expect(find.text('Quick video scan preview'), findsOneWidget);
      await returnToOverview();

      await tapAction('overview-investigation-action');
      expect(find.text('Investigations'), findsWidgets);
      await returnToOverview();

      await tapAction('overview-activity-action');
      expect(find.text('Activity'), findsWidgets);
      expect(find.textContaining('Live detections'), findsWidgets);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('desktop sidebar collapses to compact navigation', (
    tester,
  ) async {
    SharedPreferences.setMockInitialValues({});
    await _setViewport(tester, const Size(1440, 900));
    await tester.pumpWidget(const FaceSecurityApp());
    await tester.pumpAndSettle();

    final sidebar = find.byKey(const ValueKey('desktop-sidebar'));
    expect(tester.getSize(sidebar).width, 260);

    await tester.tap(find.byIcon(Icons.keyboard_double_arrow_left));
    await tester.pumpAndSettle();

    expect(tester.getSize(sidebar).width, 80);
    expect(find.byIcon(Icons.keyboard_double_arrow_right), findsOneWidget);

    await _tapDestination(tester, Icons.people_alt_outlined);
    expect(
      find.descendant(of: sidebar, matching: find.byIcon(Icons.people_alt)),
      findsOneWidget,
    );

    await tester.tap(find.byIcon(Icons.keyboard_double_arrow_right));
    await tester.pumpAndSettle();
    expect(tester.getSize(sidebar).width, 260);
  });

  final monitorViewports = <String, ({Size size, bool split})>{
    '390x844': (size: const Size(390, 844), split: false),
    '768x1024': (size: const Size(768, 1024), split: false),
    '1280x720': (size: const Size(1280, 720), split: true),
    '1440x900': (size: const Size(1440, 900), split: true),
  };

  for (final entry in monitorViewports.entries) {
    testWidgets(
      'Monitor prioritizes the preview without overflow at ${entry.key}',
      (tester) async {
        SharedPreferences.setMockInitialValues({'app_language': 'en'});
        await _setViewport(tester, entry.value.size);
        await tester.pumpWidget(const FaceSecurityApp());
        await tester.pump();

        await _tapDestination(tester, Icons.videocam_outlined);
        await tester.pump(const Duration(milliseconds: 300));

        final preview = find.byKey(const ValueKey('monitor-preview-panel'));
        final secondary = find.byKey(const ValueKey('monitor-secondary-panel'));
        expect(preview, findsOneWidget);
        expect(secondary, findsOneWidget);

        if (entry.value.split) {
          expect(tester.getTopLeft(preview).dy, lessThan(300));
          expect(
            find.byKey(const ValueKey('monitor-split-layout')),
            findsOneWidget,
          );
          expect(
            tester.getTopLeft(preview).dx,
            lessThan(tester.getTopLeft(secondary).dx),
          );
          expect(
            tester.getTopLeft(preview).dy,
            tester.getTopLeft(secondary).dy,
          );
        } else {
          expect(
            tester.getTopLeft(preview).dy,
            lessThan(entry.value.size.height / 2),
          );
          expect(
            find.byKey(const ValueKey('monitor-stacked-layout')),
            findsOneWidget,
          );
          expect(
            tester.getTopLeft(preview).dy,
            lessThan(tester.getTopLeft(secondary).dy),
          );
        }

        expect(tester.takeException(), isNull);

        await tester.tap(find.text('Quick video scan').first);
        await tester.pump();

        expect(find.text('Quick video scan preview'), findsOneWidget);
        expect(
          tester.getTopLeft(preview).dy,
          lessThanOrEqualTo(tester.getTopLeft(secondary).dy),
        );
        expect(tester.takeException(), isNull);
      },
    );
  }

  testWidgets('empty Investigations progressively hides the video rail', (
    tester,
  ) async {
    SharedPreferences.setMockInitialValues({});
    await _setViewport(tester, const Size(1440, 900));
    await tester.pumpWidget(const FaceSecurityApp());
    await tester.pump();

    await _tapDestination(tester, Icons.psychology_outlined);
    await tester.pump(const Duration(milliseconds: 300));

    expect(find.byKey(const ValueKey('video-rail')), findsNothing);
    expect(find.text('Add video'), findsOneWidget);
    expect(
      find.byKey(const ValueKey('investigations-toolbar-add-video')),
      findsNothing,
    );
  });

  testWidgets('conversation history opens at a readable desktop width', (
    tester,
  ) async {
    SharedPreferences.setMockInitialValues({'app_language': 'en'});
    await _setViewport(tester, const Size(1440, 900));
    await tester.pumpWidget(const FaceSecurityApp());
    await tester.pump();

    await _tapDestination(tester, Icons.psychology_outlined);
    await tester.pump(const Duration(milliseconds: 300));
    await tester.tap(find.byIcon(Icons.history_rounded));
    await tester.pump();

    final historySidebar = find.byKey(
      const ValueKey('conversation-history-sidebar'),
    );
    expect(historySidebar, findsOneWidget);
    expect(tester.getSize(historySidebar).width, inInclusiveRange(280, 340));
    expect(find.text('Conversation history'), findsOneWidget);
  });

  testWidgets('video QA empty state is fully translated to English', (
    tester,
  ) async {
    SharedPreferences.setMockInitialValues({'app_language': 'en'});
    await _setViewport(tester, const Size(1440, 900));
    await tester.pumpWidget(const FaceSecurityApp());
    await tester.pump();

    await _tapDestination(tester, Icons.psychology_outlined);
    await tester.pump(const Duration(milliseconds: 300));

    expect(find.text('Investigations'), findsWidgets);
    expect(
      find.text(
        'Upload and index videos persistently for deeper security-event analysis and Q&A. Indexed incidents appear in Activity.',
      ),
      findsOneWidget,
    );
    expect(find.text('Add video'), findsOneWidget);
    expect(find.text('Add your first investigation video'), findsOneWidget);
    expect(find.text('Upload and index video'), findsNothing);
    expect(find.text('No videos yet'), findsNothing);
    expect(find.text('Suggestions'), findsNothing);
    expect(
      find.text('Did anyone take the backpack from the table?'),
      findsNothing,
    );
    expect(find.text('Điều tra'), findsNothing);
    expect(find.text('Thêm video'), findsNothing);
    expect(find.text('Chưa có video'), findsNothing);
    expect(find.text('Gợi ý'), findsNothing);
  });
}

Future<void> _setViewport(WidgetTester tester, Size size) async {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = size;
  addTearDown(() {
    tester.view.resetPhysicalSize();
    tester.view.resetDevicePixelRatio();
  });
}

Future<void> _tapDestination(WidgetTester tester, IconData icon) async {
  final sidebar = find.byKey(const ValueKey('desktop-sidebar'));
  final finder = sidebar.evaluate().isNotEmpty
      ? find.descendant(of: sidebar, matching: find.byIcon(icon))
      : find.descendant(
          of: find.byType(NavigationBar),
          matching: find.byIcon(icon),
        );
  expect(finder, findsWidgets);
  await tester.tap(finder.first);
  await tester.pump();
}
