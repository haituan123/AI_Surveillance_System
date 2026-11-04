import 'dart:typed_data';

import 'package:app_flutter/services/security_service.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  test('parses camera and surveillance contracts', () async {
    final client = MockClient((request) async {
      if (request.url.path == '/cameras') {
        return http.Response(
          '[{"id":1,"name":"Laptop webcam","source":"0",'
          '"location":"Desk","is_active":true,'
          '"created_at":"now","updated_at":"now"}]',
          200,
        );
      }
      return http.Response(
        '{"state":"running","running":true,"camera_id":1,"session_id":4,'
        '"frames_processed":25,"fps":12.5,"started_at":"now",'
        '"error_message":null}',
        200,
      );
    });
    final service = SecurityService(
      client: client,
      baseUrl: 'http://backend.test',
    );

    final cameras = await service.listCameras();
    final status = await service.surveillanceStatus();

    expect(cameras.single.source, '0');
    expect(status.running, isTrue);
    expect(status.sessionId, 4);
    expect(status.fps, 12.5);
  });

  test('temporary video results preserve the non-persistent marker', () async {
    final client = MockClient(
      (request) async => http.Response(
        '{"job_id":"job-1","filename":"demo.mp4","state":"completed",'
        '"persistent":false,"summary":{"total_frames":5,'
        '"duration_seconds":1.0,"average_processing_fps":5.0,'
        '"known_events":1,"unknown_events":0,"events_truncated":false},'
        '"events":[{"frame_index":3,"timestamp_seconds":0.6,"track_id":2,'
        '"status":"known","member_id":1,"member_name":"Tuan",'
        '"similarity":0.91,"event_type":"known_identity"}],'
        '"error_message":null}',
        200,
      ),
    );
    final service = SecurityService(
      client: client,
      baseUrl: 'http://backend.test',
    );

    final results = await service.videoResults('job-1');

    expect(results.persistent, isFalse);
    expect(results.knownEvents, 1);
    expect(results.events.single.memberName, 'Tuan');
  });

  test('temporary video results parse knife evidence metadata', () async {
    final client = MockClient(
      (request) async => http.Response(
        '{"job_id":"job-knife","filename":"knife.mp4","state":"completed",'
        '"persistent":false,"summary":{"total_frames":5,'
        '"duration_seconds":1.0,"average_processing_fps":5.0,'
        '"known_events":0,"unknown_events":0,"threat_events":1,'
        '"events_truncated":false},'
        '"events":[{"event_id":"event-1","frame_index":3,'
        '"timestamp_seconds":0.6,"track_id":null,"status":null,'
        '"member_id":null,"member_name":null,"similarity":null,'
        '"event_type":"knife_threat","detected_label":"knife",'
        '"confidence":0.91,"bounding_box":[2,3,8,12],'
        '"description":"Person detected holding a knife",'
        '"is_threat":true,'
        '"snapshot_url":"/video-analysis/job-knife/events/event-1/snapshot"}],'
        '"error_message":null}',
        200,
      ),
    );
    final service = SecurityService(
      client: client,
      baseUrl: 'http://backend.test',
    );

    final results = await service.videoResults('job-knife');
    final event = results.events.single;

    expect(results.threatEvents, 1);
    expect(event.isThreat, isTrue);
    expect(event.eventType, 'knife_threat');
    expect(event.detectedLabel, 'knife');
    expect(event.confidence, 0.91);
    expect(event.boundingBox, [2, 3, 8, 12]);
    expect(event.snapshotUrl, contains('/events/event-1/snapshot'));
  });

  test('latest analysis preserves backend track ids', () async {
    final client = MockClient(
      (request) async => http.Response(
        '{"frame_index":9,"width":640,"height":480,'
        '"tracks":[{"track_id":7,"status":"unknown",'
        '"person_confidence":0.83,'
        '"bounding_box":{"x1":10,"y1":20,"x2":110,"y2":180},'
        '"member_name":null,"similarity":0.18}]}',
        200,
      ),
    );
    final service = SecurityService(
      client: client,
      baseUrl: 'http://backend.test',
    );

    final latest = await service.latestAnalysis();

    expect(latest?.tracks.single.trackId, 7);
    expect(latest?.tracks.single.status, 'unknown');
  });

  test('submitVideo uploads byte-backed picked videos', () async {
    late http.Request capturedRequest;
    final client = MockClient((request) async {
      capturedRequest = request;
      return http.Response(
        '{"job_id":"job-1","filename":"demo.mp4","state":"queued",'
        '"persistent":true,"processed_frames":0,"total_frames":null,'
        '"progress":null,"processing_fps":0.0,"error_message":null}',
        200,
      );
    });
    final service = SecurityService(
      client: client,
      baseUrl: 'http://backend.test',
    );

    final status = await service.submitVideo(
      bytes: Uint8List.fromList([1, 2, 3]),
      filename: 'demo.mp4',
    );

    expect(status.jobId, 'job-1');
    expect(capturedRequest.method, 'POST');
    expect(capturedRequest.url.path, '/video-analysis');
    expect(
      capturedRequest.headers['content-type'],
      contains('multipart/form-data'),
    );
    expect(
      String.fromCharCodes(capturedRequest.bodyBytes),
      contains('demo.mp4'),
    );
  });

  test('submitVideo uploads stream-backed picked videos', () async {
    late http.Request capturedRequest;
    final client = MockClient((request) async {
      capturedRequest = request;
      return http.Response(
        '{"job_id":"job-2","filename":"stream.mp4","state":"queued",'
        '"persistent":true,"processed_frames":0,"total_frames":null,'
        '"progress":null,"processing_fps":0.0,"error_message":null}',
        200,
      );
    });
    final service = SecurityService(
      client: client,
      baseUrl: 'http://backend.test',
    );

    final status = await service.submitVideo(
      stream: Stream<List<int>>.fromIterable([
        [1, 2],
        [3],
      ]),
      length: 3,
      filename: 'stream.mp4',
    );

    expect(status.jobId, 'job-2');
    expect(capturedRequest.method, 'POST');
    expect(capturedRequest.url.path, '/video-analysis');
    expect(
      capturedRequest.headers['content-type'],
      contains('multipart/form-data'),
    );
    expect(
      String.fromCharCodes(capturedRequest.bodyBytes),
      contains('stream.mp4'),
    );
  });

  test('backend detail becomes an ApiException', () async {
    final client = MockClient(
      (request) async =>
          http.Response('{"detail":"Stop live surveillance first"}', 409),
    );
    final service = SecurityService(
      client: client,
      baseUrl: 'http://backend.test',
    );

    expect(
      service.startSurveillance(1),
      throwsA(
        isA<ApiException>().having(
          (error) => error.message,
          'message',
          'Stop live surveillance first',
        ),
      ),
    );
  });

  test('deleteLog calls the persistent log delete endpoint', () async {
    Uri? requestedUrl;
    final client = MockClient((request) async {
      requestedUrl = request.url;
      return http.Response(
        '{"message":"Detection log deleted",'
        '"deleted_log_id":7,"deleted_snapshot":true}',
        200,
      );
    });
    final service = SecurityService(
      client: client,
      baseUrl: 'http://backend.test',
    );

    await service.deleteLog(7);

    expect(requestedUrl?.path, '/logs/7');
  });

  test('parses persistent logs and linked alerts', () async {
    final client = MockClient((request) async {
      if (request.url.path == '/logs') {
        return http.Response(
          '[{"id":11,"session_id":3,"camera_id":1,"member_id":null,'
          '"track_id":4,"status":"unknown","confidence":0.22,'
          '"snapshot_path":null,"detected_at":"2026-08-18T01:00:00Z",'
          '"member_name":null,"camera_name":"Laptop webcam"}]',
          200,
        );
      }
      return http.Response(
        '[{"id":12,"session_id":3,"camera_id":1,"detection_log_id":11,'
        '"member_id":null,"alert_type":"unknown_person",'
        '"message":"Unknown person detected","confidence":0.22,'
        '"snapshot_path":null,"is_read":false,'
        '"created_at":"2026-08-18T01:00:00Z","member_name":null,'
        '"camera_name":"Laptop webcam","snapshot_url":null}]',
        200,
      );
    });
    final service = SecurityService(
      client: client,
      baseUrl: 'http://backend.test',
    );

    final logs = await service.listLogs();
    final alerts = await service.listAlerts();

    expect(logs.single.sessionId, 3);
    expect(logs.single.trackId, 4);
    expect(logs.single.status, 'unknown');
    expect(alerts.single.detectionLogId, 11);
  });

  test('delete helpers call persistent delete endpoints', () async {
    final requestedPaths = <String>[];
    final client = MockClient((request) async {
      requestedPaths.add(request.url.path);
      return http.Response('{}', 200);
    });
    final service = SecurityService(
      client: client,
      baseUrl: 'http://backend.test',
    );

    await service.deleteAllLogs();
    await service.deleteAlert(8);
    await service.deleteAllAlerts();

    expect(requestedPaths, ['/logs/all', '/alerts/8', '/alerts/all']);
  });
}
