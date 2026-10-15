import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import '../core/api_config.dart';
import '../models/qa_models.dart';
import 'security_service.dart';

class QAService {
  QAService({http.Client? client, String? baseUrl})
      : _client = client ?? http.Client(),
        baseUrl = baseUrl ?? ApiConfig.baseUrl;

  final http.Client _client;
  final String baseUrl;
  static const _requestTimeout = Duration(seconds: 25);

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

  Future<http.Response> _delete(Uri uri) =>
      _client.delete(uri).timeout(_requestTimeout);

  void _ensureSuccess(http.Response response) {
    if (response.statusCode >= 200 && response.statusCode < 300) {
      return;
    }
    String message = 'Yêu cầu thất bại (${response.statusCode})';
    try {
      final decoded = jsonDecode(response.body);
      if (decoded is Map<String, dynamic> && decoded['detail'] != null) {
        message = decoded['detail'].toString();
      }
    } catch (_) {}
    throw ApiException(message, statusCode: response.statusCode);
  }

  Future<List<QAConversationModel>> listConversations() async {
    final response = await _get(_uri('/qa/conversations'));
    _ensureSuccess(response);
    final List<dynamic> list = jsonDecode(response.body) as List<dynamic>;
    return list
        .map((e) => QAConversationModel.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<QAConversationModel> createConversation({String? title}) async {
    final response = await _post(
      _uri('/qa/conversations'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'title': title ?? 'Phiên hỏi đáp an ninh'}),
    );
    _ensureSuccess(response);
    return QAConversationModel.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<QAConversationDetailModel> getConversationDetail(int id) async {
    final response = await _get(_uri('/qa/conversations/$id'));
    _ensureSuccess(response);
    return QAConversationDetailModel.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<void> deleteConversation(int id) async {
    final response = await _delete(_uri('/qa/conversations/$id'));
    _ensureSuccess(response);
  }

  Future<QAMessageModel> askQuestion({
    required String question,
    int? conversationId,
    int? cameraId,
    String? sessionOrVideoId,
  }) async {
    final response = await _post(
      _uri('/qa/ask'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'question': question,
        'conversation_id': conversationId,
        'camera_id': cameraId,
        'session_or_video_id': sessionOrVideoId,
      }),
    );
    _ensureSuccess(response);
    return QAMessageModel.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  // ==================== VIDEO UPLOAD METHODS ====================

  Future<QAUploadedVideoModel> uploadVideo({
    required int conversationId,
    required String filePath,
    String? filename,
  }) async {
    final uri = _uri('/qa/conversations/$conversationId/videos');
    final request = http.MultipartRequest('POST', uri);

    final file = await http.MultipartFile.fromPath(
      'file',
      filePath,
      filename: filename,
    );
    request.files.add(file);

    final streamedResponse = await request.send().timeout(const Duration(minutes: 5));
    final response = await http.Response.fromStream(streamedResponse);
    _ensureSuccess(response);

    return QAUploadedVideoModel.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<List<QAUploadedVideoModel>> listUploadedVideos(int conversationId) async {
    final response = await _get(_uri('/qa/conversations/$conversationId/videos'));
    _ensureSuccess(response);
    final List<dynamic> list = jsonDecode(response.body) as List<dynamic>;
    return list
        .map((e) => QAUploadedVideoModel.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<QAUploadedVideoModel> getVideoStatus(String videoId) async {
    final response = await _get(_uri('/qa/videos/$videoId/status'));
    _ensureSuccess(response);
    return QAUploadedVideoModel.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<void> deleteUploadedVideo(String videoId) async {
    final response = await _delete(_uri('/qa/videos/$videoId'));
    _ensureSuccess(response);
  }

  Future<QAUploadedVideoModel> retryVideo(String videoId) async {
    final response = await _post(_uri('/qa/videos/$videoId/retry'));
    _ensureSuccess(response);
    return QAUploadedVideoModel.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }
}
