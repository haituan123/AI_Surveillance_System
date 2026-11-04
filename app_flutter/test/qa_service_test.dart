import 'dart:typed_data';

import 'package:app_flutter/services/qa_service.dart';
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
}
