import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

import '../core/api_config.dart';
import '../models/security_models.dart';

class ApiException implements Exception {
  const ApiException(this.message, {this.statusCode});

  final String message;
  final int? statusCode;

  @override
  String toString() => message;
}

class SecurityService {
  SecurityService({http.Client? client, String? baseUrl})
      : _client = client ?? http.Client(),
        baseUrl = baseUrl ?? ApiConfig.baseUrl;

  final http.Client _client;
  final String baseUrl;
  static const _requestTimeout = Duration(seconds: 4);
  static const _uploadTimeout = Duration(seconds: 60);

  Uri _uri(String path, [Map<String, String>? query]) =>
      Uri.parse('$baseUrl$path').replace(queryParameters: query);

  Future<http.Response> _get(Uri uri) =>
      _client.get(uri).timeout(_requestTimeout);

  Future<http.Response> _post(
    Uri uri, {
    Map<String, String>? headers,
    Object? body,
  }) =>
      _client.post(uri, headers: headers, body: body).timeout(_requestTimeout);

  Future<http.Response> _patch(
    Uri uri, {
    Map<String, String>? headers,
    Object? body,
  }) =>
      _client.patch(uri, headers: headers, body: body).timeout(_requestTimeout);

  Future<http.Response> _delete(Uri uri) =>
      _client.delete(uri).timeout(_requestTimeout);

  Future<bool> health() async {
    final response = await _get(_uri('/health'));
    _ensureSuccess(response);
    return true;
  }

  Future<List<CameraModel>> listCameras() async {
    final response = await _get(_uri('/cameras'));
    _ensureSuccess(response);
    return (_jsonList(response))
        .map((item) => CameraModel.fromJson(item as Map<String, dynamic>))
        .toList();
  }

  Future<CameraModel> addLaptopWebcam() async {
    final response = await _post(
      _uri('/cameras'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'name': 'Laptop webcam',
        'source': '0',
        'location': 'This laptop',
      }),
    );
    _ensureSuccess(response);
    return CameraModel.fromJson(_jsonMap(response));
  }

  Future<SurveillanceStatusModel> surveillanceStatus() async {
    final response = await _get(_uri('/surveillance/status'));
    _ensureSuccess(response);
    return SurveillanceStatusModel.fromJson(_jsonMap(response));
  }

  Future<SurveillanceStatusModel> startSurveillance(int cameraId) async {
    final response = await _post(
      _uri('/surveillance/start'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'camera_id': cameraId}),
    );
    _ensureSuccess(response);
    return SurveillanceStatusModel.fromJson(_jsonMap(response));
  }

  Future<SurveillanceStatusModel> stopSurveillance() async {
    final response = await _post(_uri('/surveillance/stop'));
    _ensureSuccess(response);
    return SurveillanceStatusModel.fromJson(_jsonMap(response));
  }

  Future<LatestAnalysisModel?> latestAnalysis() async {
    final response = await _get(_uri('/surveillance/latest'));
    if (response.statusCode == 404) return null;
    _ensureSuccess(response);
    return LatestAnalysisModel.fromJson(_jsonMap(response));
  }

  Future<Uint8List?> liveFrame() async {
    final response = await _get(_uri('/surveillance/frame'));
    if (response.statusCode == 404) return null;
    _ensureSuccess(response);
    return response.bodyBytes;
  }

  Future<List<ZoneModel>> listZones(int cameraId) async {
    final response = await _get(
      _uri('/zones', {
        'camera_id': cameraId.toString(),
        'include_inactive': 'true',
      }),
    );
    _ensureSuccess(response);
    return _jsonList(
      response,
    ).map((item) => ZoneModel.fromJson(item as Map<String, dynamic>)).toList();
  }

  Future<ZoneModel> createZone({
    required int cameraId,
    required String name,
    required List<ZonePointModel> points,
  }) async {
    final response = await _post(
      _uri('/zones'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'camera_id': cameraId,
        'name': name,
        'points': points.map((point) => point.toJson()).toList(),
      }),
    );
    _ensureSuccess(response);
    return ZoneModel.fromJson(_jsonMap(response));
  }

  Future<ZoneModel> setZoneActive(int zoneId, bool isActive) async {
    final response = await _patch(
      _uri('/zones/$zoneId'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'is_active': isActive}),
    );
    _ensureSuccess(response);
    return ZoneModel.fromJson(_jsonMap(response));
  }

  Future<void> deleteZone(int zoneId) async {
    final response = await _delete(_uri('/zones/$zoneId'));
    _ensureSuccess(response);
  }

  Future<VideoAnalysisStatusModel> submitVideo({
    String? path,
    Stream<List<int>>? stream,
    int? length,
    Uint8List? bytes,
    required String filename,
  }) async {
    final request = http.MultipartRequest('POST', _uri('/video-analysis'));
    if (stream != null && length != null) {
      request.files.add(
        http.MultipartFile(
          'file',
          http.ByteStream(stream),
          length,
          filename: filename,
        ),
      );
    } else if (bytes != null) {
      request.files.add(
        http.MultipartFile.fromBytes('file', bytes, filename: filename),
      );
    } else if (path != null) {
      request.files.add(
        await http.MultipartFile.fromPath('file', path, filename: filename),
      );
    } else {
      throw const ApiException('Selected video data is not available.');
    }
    final streamed = await _client.send(request).timeout(_uploadTimeout);
    final response = await http.Response.fromStream(streamed);
    _ensureSuccess(response);
    return VideoAnalysisStatusModel.fromJson(_jsonMap(response));
  }

  Future<VideoAnalysisStatusModel> videoStatus(String jobId) async {
    final response = await _get(_uri('/video-analysis/$jobId/status'));
    _ensureSuccess(response);
    return VideoAnalysisStatusModel.fromJson(_jsonMap(response));
  }

  Future<VideoAnalysisResultsModel> videoResults(String jobId) async {
    final response = await _get(_uri('/video-analysis/$jobId/results'));
    _ensureSuccess(response);
    return VideoAnalysisResultsModel.fromJson(_jsonMap(response));
  }

  Future<Uint8List?> videoFrame(String jobId) async {
    final response = await _get(_uri('/video-analysis/$jobId/frame'));
    if (response.statusCode == 404) return null;
    _ensureSuccess(response);
    return response.bodyBytes;
  }

  Future<void> deleteVideoJob(String jobId) async {
    final response = await _delete(_uri('/video-analysis/$jobId'));
    _ensureSuccess(response);
  }

  Future<List<DetectionLogModel>> listLogs({int limit = 100}) async {
    final response = await _get(_uri('/logs', {'limit': limit.toString()}));
    _ensureSuccess(response);
    return _jsonList(response)
        .map((item) => DetectionLogModel.fromJson(item as Map<String, dynamic>))
        .toList();
  }

  Future<void> deleteLog(int logId) async {
    final response = await _delete(_uri('/logs/$logId'));
    _ensureSuccess(response);
  }

  Future<void> deleteAllLogs() async {
    final response = await _delete(_uri('/logs/all'));
    _ensureSuccess(response);
  }

  Future<List<SecurityEventModel>> listSecurityEvents({int limit = 200}) async {
    final response = await _get(
      _uri('/logs/security-events', {'limit': limit.toString()}),
    );
    _ensureSuccess(response);
    return _jsonList(response)
        .map(
          (item) => SecurityEventModel.fromJson(item as Map<String, dynamic>),
        )
        .toList();
  }

  Future<List<AlertModel>> listAlerts({int limit = 100}) async {
    final response = await _get(_uri('/alerts', {'limit': limit.toString()}));
    _ensureSuccess(response);
    return _jsonList(
      response,
    ).map((item) => AlertModel.fromJson(item as Map<String, dynamic>)).toList();
  }

  Future<AlertModel> setAlertRead(int alertId, bool isRead) async {
    final response = await _patch(
      _uri('/alerts/$alertId/read'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'is_read': isRead}),
    );
    _ensureSuccess(response);
    return AlertModel.fromJson(_jsonMap(response));
  }

  Future<void> deleteAlert(int alertId) async {
    final response = await _delete(_uri('/alerts/$alertId'));
    _ensureSuccess(response);
  }

  Future<void> deleteAllAlerts() async {
    final response = await _delete(_uri('/alerts/all'));
    _ensureSuccess(response);
  }

  String alertSnapshotUrl(int alertId) => '$baseUrl/alerts/$alertId/snapshot';

  static Map<String, dynamic> _jsonMap(http.Response response) =>
      jsonDecode(response.body) as Map<String, dynamic>;

  static List<dynamic> _jsonList(http.Response response) =>
      jsonDecode(response.body) as List<dynamic>;

  static void _ensureSuccess(http.Response response) {
    if (response.statusCode >= 200 && response.statusCode < 300) return;
    var message = 'Backend request failed (${response.statusCode}).';
    try {
      final body = jsonDecode(response.body) as Map<String, dynamic>;
      if (body['detail'] is String) message = body['detail'] as String;
    } catch (_) {
      // Keep the status-based fallback for non-JSON errors.
    }
    throw ApiException(message, statusCode: response.statusCode);
  }
}
