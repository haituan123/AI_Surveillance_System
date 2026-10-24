import 'package:app_flutter/app.dart';
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

      expect(find.text('Operational Overview'), findsOneWidget);
      expect(find.text('Dashboard'), findsWidgets);
      expect(find.text('Members'), findsWidgets);
      expect(find.text('Register'), findsWidgets);
      expect(find.text('Surveillance'), findsWidgets);
      expect(find.text('Logs'), findsWidgets);

      await _tapDestination(tester, Icons.person_add_alt_1_outlined);
      expect(tester.takeException(), isNull, reason: 'register overflow');
      expect(find.text('Person details'), findsOneWidget);
      expect(find.text('No images selected'), findsOneWidget);

      await _tapDestination(tester, Icons.videocam_outlined);
      expect(tester.takeException(), isNull, reason: 'surveillance overflow');
      expect(find.text('Surveillance'), findsWidgets);
      expect(find.text('Camera preview'), findsOneWidget);

      await _tapDestination(tester, Icons.receipt_long_outlined);
      expect(tester.takeException(), isNull, reason: 'logs overflow');
      expect(find.text('Persistent Logs & Alerts'), findsOneWidget);
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
    expect(find.text('Tổng quan vận hành'), findsOneWidget);

    await tester.tap(find.text('Tối'));
    await tester.pumpAndSettle();
    final app = tester.widget<MaterialApp>(find.byType(MaterialApp));
    expect(app.themeMode, ThemeMode.dark);
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
  final finder = find.byIcon(icon);
  expect(finder, findsWidgets);
  await tester.tap(finder.first);
  await tester.pump();
}
