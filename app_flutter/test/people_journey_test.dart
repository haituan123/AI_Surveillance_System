import 'dart:convert';
import 'dart:typed_data';

import 'package:app_flutter/core/app_settings.dart';
import 'package:app_flutter/screens/people_screen.dart';
import 'package:app_flutter/screens/register_screen.dart';
import 'package:app_flutter/services/member_service.dart';
import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  testWidgets('register, refresh, search, and safely delete a person', (
    tester,
  ) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(1000, 900);
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });
    final members = <Map<String, Object?>>[];
    var deleteRequests = 0;
    final faceBytes = base64Decode(
      'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=',
    );
    final client = MockClient((request) async {
      if (request.method == 'GET' && request.url.path == '/members') {
        return http.Response(jsonEncode(members), 200);
      }
      if (request.method == 'POST' && request.url.path == '/members/register') {
        final member = <String, Object?>{
          'id': 7,
          'name': 'Avery Stone',
          'created_at': '2026-11-19T08:00:00Z',
          'image_count': 2,
        };
        members.add(member);
        return http.Response(
          jsonEncode({
            'member': member,
            'accepted_images': [
              {
                'filename': 'front.jpg',
                'status': 'accepted',
                'reason': 'Face embedding saved.',
              },
              {
                'filename': 'side.jpg',
                'status': 'accepted',
                'reason': 'Face embedding saved.',
              },
            ],
            'rejected_images': <Object>[],
            'message': 'Registered Avery Stone with 2 images.',
          }),
          200,
        );
      }
      if (request.method == 'DELETE' && request.url.path == '/members/7') {
        deleteRequests++;
        members.clear();
        return http.Response('{}', 200);
      }
      return http.Response('{}', 404);
    });
    final settings = AppSettingsController();
    addTearDown(settings.dispose);

    await tester.pumpWidget(
      AppSettingsScope(
        controller: settings,
        child: MaterialApp(
          home: _PeopleJourneyHost(
            service: MemberService(client: client),
            imagePicker: () async => [
              PlatformFile(
                name: 'front.jpg',
                size: faceBytes.length,
                bytes: Uint8List.fromList(faceBytes),
              ),
              PlatformFile(
                name: 'side.jpg',
                size: faceBytes.length,
                bytes: Uint8List.fromList(faceBytes),
              ),
            ],
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('No registered people'), findsOneWidget);

    await tester.tap(find.text('Register a person'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).first, 'Avery Stone');
    await tester.tap(find.text('Choose face images'));
    await tester.pumpAndSettle();
    expect(find.text('front.jpg'), findsOneWidget);
    expect(find.text('side.jpg'), findsOneWidget);

    await tester.ensureVisible(find.text('Register'));
    await tester.tap(find.text('Register'));
    await tester.pumpAndSettle();
    expect(find.text('Registered Avery Stone with 2 images.'), findsWidgets);

    await tester.tap(find.text('Registered people'));
    await tester.pumpAndSettle();
    expect(find.text('Avery Stone'), findsOneWidget);
    expect(find.text('2 images'), findsOneWidget);

    await tester.enterText(find.byType(TextField).first, 'avery');
    await tester.pump();
    expect(find.text('Avery Stone'), findsOneWidget);
    await tester.enterText(find.byType(TextField).first, 'missing');
    await tester.pump();
    expect(find.text('No matching members'), findsOneWidget);
    await tester.tap(find.text('Clear search'));
    await tester.pump();

    await tester.tap(find.byTooltip('Delete member'));
    await tester.pumpAndSettle();
    expect(find.text('Delete Avery Stone?'), findsOneWidget);
    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();
    expect(deleteRequests, 0);
    expect(find.text('Avery Stone'), findsOneWidget);

    await tester.tap(find.byTooltip('Delete member'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Delete member'));
    await tester.pumpAndSettle();
    expect(deleteRequests, 1);
    expect(find.text('No registered people'), findsOneWidget);
  });
}

class _PeopleJourneyHost extends StatefulWidget {
  const _PeopleJourneyHost({
    required this.service,
    required this.imagePicker,
  });

  final MemberService service;
  final RegistrationImagePicker imagePicker;

  @override
  State<_PeopleJourneyHost> createState() => _PeopleJourneyHostState();
}

class _PeopleJourneyHostState extends State<_PeopleJourneyHost> {
  int _refreshToken = 0;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: PeopleScreen(
        refreshToken: _refreshToken,
        onMembersChanged: () => setState(() => _refreshToken++),
        memberService: widget.service,
        imagePicker: widget.imagePicker,
      ),
    );
  }
}
