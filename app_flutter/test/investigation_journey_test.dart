import 'dart:convert';
import 'dart:typed_data';

import 'package:app_flutter/core/app_settings.dart';
import 'package:app_flutter/screens/video_qa_screen.dart';
import 'package:app_flutter/services/qa_service.dart';
import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  testWidgets('create, upload, ask, inspect evidence, and dispatch seek', (
    tester,
  ) async {
    final requestedPaths = <String>[];
    String? askedQuestion;
    String? seekVideoId;
    Duration? seekPosition;
    final conversation = {
      'id': 12,
      'title': 'Loading dock investigation',
      'created_at': '2026-11-19T08:00:00Z',
      'message_count': 0,
    };
    final video = {
      'id': 3,
      'conversation_id': 12,
      'video_id': 'video-12',
      'filename': 'loading-dock.mp4',
      'status': 'completed',
      'processed_frames': 120,
      'indexed_frames': 120,
      'total_frames': 120,
      'source_fps': 30.0,
      'analysis_fps': 6.0,
      'error_message': null,
      'created_at': '2026-11-19T08:01:00Z',
      'completed_at': '2026-11-19T08:02:00Z',
    };
    final client = MockClient((request) async {
      requestedPaths.add('${request.method} ${request.url.path}');
      if (request.method == 'GET' && request.url.path == '/qa/conversations') {
        return http.Response('[]', 200);
      }
      if (request.method == 'POST' && request.url.path == '/qa/conversations') {
        return http.Response(jsonEncode(conversation), 200);
      }
      if (request.method == 'POST' &&
          request.url.path == '/qa/conversations/12/videos') {
        return http.Response(jsonEncode(video), 200);
      }
      if (request.method == 'POST' && request.url.path == '/qa/ask') {
        final body = jsonDecode(request.body) as Map<String, dynamic>;
        askedQuestion = body['question'] as String?;
        return http.Response(jsonEncode(_answer), 200);
      }
      return http.Response('{}', 404);
    });
    final settings = AppSettingsController();
    addTearDown(settings.dispose);
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(1440, 900);
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });
    final videoBytes = Uint8List.fromList([1, 2, 3, 4]);

    await tester.pumpWidget(
      AppSettingsScope(
        controller: settings,
        child: MaterialApp(
          home: VideoQAScreen(
            service: QAService(client: client),
            initializeVideoPlayers: false,
            videoPicker: () async => PlatformFile(
              name: 'loading-dock.mp4',
              size: videoBytes.length,
              bytes: videoBytes,
            ),
            onEvidenceSeek: (videoId, position) {
              seekVideoId = videoId;
              seekPosition = position;
            },
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Add video'), findsOneWidget);

    await tester.tap(find.text('Add video'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Selected: loading-dock.mp4'), findsWidgets);
    expect(find.textContaining('Ready'), findsWidgets);
    expect(
      requestedPaths,
      containsAll([
        'POST /qa/conversations',
        'POST /qa/conversations/12/videos',
      ]),
    );
    await tester.pump(const Duration(seconds: 4));
    await tester.pumpAndSettle();

    final questionField = find.byType(TextField).last;
    await tester.enterText(questionField, 'Was a weapon visible?');
    expect(find.byTooltip('Ask question'), findsOneWidget);
    await tester.tap(find.byIcon(Icons.arrow_upward_rounded));
    await tester.pumpAndSettle();
    expect(askedQuestion, 'Was a weapon visible?');
    expect(find.text('A knife was visible near the loading dock.'),
        findsOneWidget);
    expect(find.text('Confidence 93.0%'), findsOneWidget);
    expect(find.text('loading-dock.mp4'), findsWidgets);
    expect(find.textContaining('00:05 – 00:07'), findsWidgets);
    expect(find.text('Technical details'), findsOneWidget);

    await tester.tap(find.textContaining('Open video at').first);
    await tester.pump();
    expect(seekVideoId, 'video-12');
    expect(seekPosition, const Duration(seconds: 5));
  });
}

const _answer = {
  'id': 44,
  'conversation_id': 12,
  'user_query_vi': 'Was a weapon visible?',
  'translated_query_en': 'Was a weapon visible?',
  'reasoning_en': 'The indexed frames show a knife.',
  'response_vi': 'A knife was visible near the loading dock.',
  'question_type': 'weapon',
  'created_at': '2026-11-19T08:03:00Z',
  'evidences': [
    {
      'id': 45,
      'message_id': 44,
      'start_timestamp': 5.0,
      'end_timestamp': 7.0,
      'snapshot_path': '',
      'event_type': 'weapon_present',
      'detected_label': 'knife',
      'confidence': 0.93,
      'source_video_id': 'video-12',
    },
  ],
};
