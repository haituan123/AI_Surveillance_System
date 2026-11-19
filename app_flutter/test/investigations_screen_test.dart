import 'dart:convert';

import 'package:app_flutter/core/app_settings.dart';
import 'package:app_flutter/screens/video_qa_screen.dart';
import 'package:app_flutter/services/qa_service.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  testWidgets('empty state shows exactly one primary Add video action', (
    tester,
  ) async {
    await _pumpInvestigations(tester, videos: const []);

    expect(find.text('Add video'), findsOneWidget);
    expect(
      find.byKey(const ValueKey('investigations-empty-add-video')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey('investigations-toolbar-add-video')),
      findsNothing,
    );
    expect(find.byKey(const ValueKey('video-rail')), findsNothing);
    expect(find.byKey(const ValueKey('investigations-video-library')),
        findsNothing);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  for (final state in const ['processing', 'failed']) {
    testWidgets('single $state video keeps one compact toolbar action', (
      tester,
    ) async {
      await _pumpInvestigations(
        tester,
        videos: [_video(state: state, filename: '$state.mp4')],
      );

      expect(find.text('Add video'), findsOneWidget);
      expect(
        find.byKey(const ValueKey('investigations-toolbar-add-video')),
        findsOneWidget,
      );
      expect(
        find.byKey(const ValueKey('investigations-empty-add-video')),
        findsNothing,
      );
      expect(
        find.byKey(const ValueKey('investigations-single-video-menu')),
        findsOneWidget,
      );
      expect(
        find.byKey(const ValueKey('investigations-video-library')),
        findsNothing,
      );
      expect(
        find.textContaining(state == 'failed' ? 'Failed' : 'Processing'),
        findsWidgets,
      );

      await tester.tap(
        find.byKey(const ValueKey('investigations-single-video-menu')),
      );
      await tester.pumpAndSettle();
      expect(
        find.text('Retry analysis'),
        state == 'failed' ? findsOneWidget : findsNothing,
      );
      expect(find.text('Delete video and related data'), findsOneWidget);
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox.shrink());
    });
  }

  testWidgets(
      'completed video prioritizes answer, evidence, and collapsed details', (
    tester,
  ) async {
    await _pumpInvestigations(
      tester,
      videos: [_video(state: 'completed', filename: 'clip.mp4')],
      messages: [_completedMessage()],
    );

    expect(find.textContaining('Selected: clip.mp4'), findsWidgets);
    expect(find.textContaining('Ready'), findsWidgets);
    expect(find.text('The answer is shown first.'), findsOneWidget);
    expect(find.text('Technical details'), findsOneWidget);
    expect(find.textContaining('Model reasoning'), findsNothing);
    expect(find.textContaining('00:02 – 00:04'), findsWidgets);
    expect(find.text('Confidence 91.0%'), findsOneWidget);
    expect(find.text('clip.mp4'), findsWidgets);

    await tester.tap(find.text('Technical details'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Model reasoning'), findsOneWidget);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('multiple videos reveal library management and all-video scope', (
    tester,
  ) async {
    await _pumpInvestigations(
      tester,
      videos: [
        _video(state: 'completed', filename: 'front-door.mp4', id: 1),
        _video(state: 'completed', filename: 'lobby.mp4', id: 2),
      ],
    );

    expect(find.text('Add video'), findsOneWidget);
    expect(find.textContaining('Scope: All videos (2)'), findsWidgets);
    expect(
      find.byKey(const ValueKey('investigations-video-library')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey('investigations-single-video-menu')),
      findsNothing,
    );

    final videoRail = find.byKey(const ValueKey('video-rail'));
    expect(tester.getSize(videoRail).width, 360);
    await tester.tap(find.byKey(const ValueKey('collapse-video-rail')));
    await tester.pump(const Duration(milliseconds: 300));
    expect(tester.getSize(videoRail).width, 52);
    await tester.tap(find.byKey(const ValueKey('expand-video-rail')));
    await tester.pump(const Duration(milliseconds: 300));
    expect(tester.getSize(videoRail).width, 360);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('mobile keeps scope, Add video, and history accessible', (
    tester,
  ) async {
    await _pumpInvestigations(
      tester,
      size: const Size(390, 844),
      videos: [_video(state: 'completed', filename: 'mobile.mp4')],
    );

    expect(find.text('Add video'), findsOneWidget);
    expect(find.textContaining('Selected: mobile.mp4'), findsWidgets);
    expect(find.byTooltip('Conversation history'), findsOneWidget);
    expect(tester.takeException(), isNull);

    await tester.tap(find.byTooltip('Conversation history'));
    await tester.pumpAndSettle();
    expect(find.text('Conversation history'), findsOneWidget);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox.shrink());
  });
}

Future<void> _pumpInvestigations(
  WidgetTester tester, {
  required List<Map<String, Object?>> videos,
  List<Map<String, Object?>> messages = const [],
  Size size = const Size(1440, 900),
}) async {
  final conversation = {
    'id': 1,
    'title': 'Investigation',
    'created_at': '2026-11-19T08:00:00',
    'message_count': messages.length,
  };
  final client = MockClient((request) async {
    final body = switch (request.url.path) {
      '/qa/conversations' => [conversation],
      '/qa/conversations/1' => {
          'conversation': conversation,
          'messages': messages,
          'uploaded_videos': videos,
        },
      _ => <Object>[],
    };
    return http.Response(jsonEncode(body), 200);
  });
  final settings = AppSettingsController();
  addTearDown(settings.dispose);
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = size;
  addTearDown(() {
    tester.view.resetPhysicalSize();
    tester.view.resetDevicePixelRatio();
  });

  await tester.pumpWidget(
    AppSettingsScope(
      controller: settings,
      child: MaterialApp(
        home: VideoQAScreen(
          service: QAService(client: client),
          initializeVideoPlayers: false,
        ),
      ),
    ),
  );
  await tester.pump();
  await tester.pumpAndSettle();
}

Map<String, Object?> _video({
  required String state,
  required String filename,
  int id = 1,
}) =>
    {
      'id': id,
      'conversation_id': 1,
      'video_id': 'video-$id',
      'filename': filename,
      'status': state,
      'processed_frames': state == 'processing' ? 10 : 100,
      'indexed_frames': state == 'completed' ? 100 : 0,
      'total_frames': 100,
      'source_fps': 30.0,
      'analysis_fps': 5.0,
      'error_message': state == 'failed' ? 'Processing failed' : null,
      'created_at': '2026-11-19T08:00:00',
      'completed_at': state == 'completed' ? '2026-11-19T08:01:00' : null,
    };

Map<String, Object?> _completedMessage() => {
      'id': 5,
      'conversation_id': 1,
      'user_query_vi': 'What happened?',
      'translated_query_en': 'What happened?',
      'reasoning_en': 'Model reasoning stays secondary.',
      'response_vi': 'The answer is shown first.',
      'question_type': 'security',
      'created_at': '2026-11-19T08:02:00',
      'evidences': [
        {
          'id': 7,
          'message_id': 5,
          'start_timestamp': 2.0,
          'end_timestamp': 4.0,
          'snapshot_path': '',
          'event_type': 'weapon_present',
          'detected_label': 'knife',
          'confidence': 0.91,
          'source_video_id': 'video-1',
        },
      ],
    };
