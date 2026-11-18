import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:app_flutter/services/qa_service.dart';
import 'package:app_flutter/services/security_service.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

const _uploadedVideoResponse =
    '{"id":1,"conversation_id":7,"video_id":"video-1",'
    '"filename":"demo.mp4","status":"queued","processed_frames":0,'
    '"indexed_frames":0,"total_frames":null,"source_fps":30.0,'
    '"analysis_fps":7.5,"error_message":null,"created_at":"now",'
    '"completed_at":null}';

void main() {
  test(
    'askQuestion sends bounded multi-video scope and parses evidence source',
    () async {
      late http.Request capturedRequest;
      final client = MockClient((request) async {
        capturedRequest = request;
        return http.Response.bytes(
          utf8.encode(
            jsonEncode({
              'id': 9,
              'conversation_id': 7,
              'user_query_vi': 'Ai xuất hiện?',
              'translated_query_en': 'Who appears?',
              'response_vi': 'Có một người.',
              'question_type': 'identity',
              'created_at': 'now',
              'evidences': [
                {
                  'id': 11,
                  'message_id': 9,
                  'frame_id': 3,
                  'start_timestamp': 4.0,
                  'end_timestamp': 4.0,
                  'snapshot_path': 'snapshot.jpg',
                  'source_video_id': 'video-2',
                },
              ],
            }),
          ),
          200,
          headers: {'content-type': 'application/json; charset=utf-8'},
        );
      });
      final service = QAService(client: client, baseUrl: 'http://backend.test');

      final answer = await service.askQuestion(
        question: 'Ai xuất hiện?',
        conversationId: 7,
        sessionOrVideoIds: const ['video-1', 'video-2'],
        responseLanguage: 'en',
      );

      final body = jsonDecode(capturedRequest.body) as Map<String, dynamic>;
      expect(body['session_or_video_ids'], ['video-1', 'video-2']);
      expect(body['response_language'], 'en');
      expect(answer.evidences.single.sourceVideoId, 'video-2');
      expect(
        service.videoContentUrl('video-2'),
        'http://backend.test/qa/videos/video-2/content',
      );
    },
  );

  test('uploadVideo uploads browser-provided bytes', () async {
    late http.Request capturedRequest;
    final client = MockClient((request) async {
      capturedRequest = request;
      return http.Response(_uploadedVideoResponse, 201);
    });
    final service = QAService(client: client, baseUrl: 'http://backend.test');

    final uploaded = await service.uploadVideo(
      conversationId: 7,
      bytes: Uint8List.fromList([1, 2, 3]),
      filename: 'demo.mp4',
    );

    expect(uploaded.videoId, 'video-1');
    expect(uploaded.sourceFps, 30.0);
    expect(uploaded.analysisFps, 7.5);
    expect(capturedRequest.method, 'POST');
    expect(capturedRequest.url.path, '/qa/conversations/7/videos');
    expect(
      capturedRequest.headers['content-type'],
      contains('multipart/form-data'),
    );
    expect(
      String.fromCharCodes(capturedRequest.bodyBytes),
      contains('demo.mp4'),
    );
  });

  test('uploadVideo uploads browser-provided stream', () async {
    late http.Request capturedRequest;
    final client = MockClient((request) async {
      capturedRequest = request;
      return http.Response(_uploadedVideoResponse, 201);
    });
    final service = QAService(client: client, baseUrl: 'http://backend.test');

    final uploaded = await service.uploadVideo(
      conversationId: 7,
      stream: Stream<List<int>>.fromIterable([
        [1, 2],
        [3],
      ]),
      length: 3,
      filename: 'demo.mp4',
    );

    expect(uploaded.videoId, 'video-1');
    expect(capturedRequest.method, 'POST');
    expect(
      String.fromCharCodes(capturedRequest.bodyBytes),
      contains('demo.mp4'),
    );
  });

  test(
    'askQuestion allows responses longer than the regular timeout',
    () async {
      final client = MockClient((request) async {
        await Future<void>.delayed(const Duration(milliseconds: 30));
        return http.Response.bytes(
          utf8.encode(
            jsonEncode({
              'id': 9,
              'conversation_id': 7,
              'user_query_vi': 'Có ai không?',
              'translated_query_en': 'Is anyone there?',
              'response_vi': 'Không phát hiện ai.',
              'question_type': 'identity',
              'created_at': 'now',
              'evidences': <dynamic>[],
            }),
          ),
          200,
          headers: {'content-type': 'application/json; charset=utf-8'},
        );
      });
      final service = QAService(
        client: client,
        baseUrl: 'http://backend.test',
        requestTimeout: const Duration(milliseconds: 5),
        askTimeout: const Duration(milliseconds: 100),
      );

      final answer = await service.askQuestion(question: 'Có ai không?');

      expect(answer.responseVi, 'Không phát hiện ai.');
    },
  );

  test('askQuestion reports a friendly timeout error', () async {
    final client = MockClient((request) async {
      await Future<void>.delayed(const Duration(milliseconds: 50));
      return http.Response('{}', 200);
    });
    final service = QAService(
      client: client,
      baseUrl: 'http://backend.test',
      askTimeout: const Duration(milliseconds: 5),
    );

    await expectLater(
      service.askQuestion(question: 'Có ai không?'),
      throwsA(
        isA<ApiException>().having(
          (error) => error.toString(),
          'message',
          'Phản hồi AI mất quá nhiều thời gian. Vui lòng thử lại.',
        ),
      ),
    );
  });
}
