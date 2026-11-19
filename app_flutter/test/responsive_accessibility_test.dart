import 'package:app_flutter/app.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  final viewports = <Size>[
    const Size(390, 844),
    const Size(430, 932),
    const Size(768, 1024),
    const Size(1280, 720),
    const Size(1440, 900),
  ];

  for (final viewport in viewports) {
    final compact = viewport.width < 720;
    final desktop = viewport.width >= 1100;
    final vietnamese =
        viewport == const Size(430, 932) || viewport == const Size(1280, 720);
    final dark =
        viewport == const Size(390, 844) || viewport == const Size(1440, 900);

    testWidgets(
      'five destinations remain usable at '
      '${viewport.width.toInt()}x${viewport.height.toInt()}',
      (tester) async {
        SharedPreferences.setMockInitialValues({
          'app_language': vietnamese ? 'vi' : 'en',
          'app_theme': dark ? 'dark' : 'light',
        });
        await _setViewport(tester, viewport);
        await tester.pumpWidget(const FaceSecurityApp());
        await tester.pump();
        await tester.pump();

        final app = tester.widget<MaterialApp>(find.byType(MaterialApp));
        expect(app.themeMode, dark ? ThemeMode.dark : ThemeMode.light);

        if (desktop) {
          expect(
            find.byKey(const ValueKey('desktop-sidebar')),
            findsOneWidget,
          );
          expect(find.byKey(const ValueKey('mobile-navigation')), findsNothing);
        } else {
          final navigation = tester.widget<NavigationBar>(
            find.byKey(const ValueKey('mobile-navigation')),
          );
          expect(navigation.destinations, hasLength(5));
          expect(
            navigation.labelBehavior,
            compact
                ? NavigationDestinationLabelBehavior.onlyShowSelected
                : NavigationDestinationLabelBehavior.alwaysShow,
          );
          for (final destination
              in find.byType(NavigationDestination).evaluate()) {
            final size = tester.getSize(find.byWidget(destination.widget));
            expect(size.width, greaterThanOrEqualTo(48));
            expect(size.height, greaterThanOrEqualTo(48));
          }
        }

        for (final icon in const [
          Icons.people_alt_outlined,
          Icons.videocam_outlined,
          Icons.psychology_outlined,
          Icons.receipt_long_outlined,
          Icons.dashboard_outlined,
        ]) {
          await _tapDestination(tester, icon);
          await tester.pump(const Duration(milliseconds: 350));
          expect(
            tester.takeException(),
            isNull,
            reason: 'overflow at $viewport while opening $icon',
          );
          if (compact && icon == Icons.receipt_long_outlined) {
            expect(
              find.text(vietnamese ? 'Phát hiện' : 'Detections'),
              findsOneWidget,
            );
            expect(
              find.text(vietnamese ? 'Cảnh báo' : 'Alerts'),
              findsOneWidget,
            );
            expect(
              find.text(vietnamese ? 'Sự cố' : 'Incidents'),
              findsOneWidget,
            );
            expect(
              tester.widget<TabBar>(find.byType(TabBar)).isScrollable,
              isFalse,
            );
          }
        }
      },
    );
  }

  testWidgets('headers expose hierarchy and desktop controls show focus', (
    tester,
  ) async {
    SharedPreferences.setMockInitialValues({
      'app_language': 'en',
      'app_theme': 'light',
    });
    await _setViewport(tester, const Size(1440, 900));
    await tester.pumpWidget(const FaceSecurityApp());
    await tester.pump();
    final semantics = tester.ensureSemantics();

    expect(
      find.text(
        'Review system health, live monitoring, recognition coverage, and recent security activity.',
      ),
      findsOneWidget,
    );
    expect(find.byIcon(Icons.security), findsWidgets);
    expect(find.bySemanticsLabel('Overview'), findsWidgets);

    await tester.sendKeyEvent(LogicalKeyboardKey.tab);
    await tester.pump();
    expect(FocusManager.instance.primaryFocus, isNotNull);
    expect(FocusManager.instance.primaryFocus!.hasFocus, isTrue);

    await tester.tap(find.byIcon(Icons.keyboard_double_arrow_left));
    await tester.pumpAndSettle();
    expect(find.byTooltip('Overview'), findsOneWidget);
    expect(find.byTooltip('People'), findsOneWidget);
    expect(find.byTooltip('Monitor'), findsOneWidget);
    expect(find.byTooltip('Investigations'), findsOneWidget);
    expect(find.byTooltip('Activity'), findsOneWidget);
    semantics.dispose();
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
          of: find.byKey(const ValueKey('mobile-navigation')),
          matching: find.byIcon(icon),
        );
  expect(finder, findsWidgets);
  await tester.tap(finder.first);
  await tester.pump();
}
