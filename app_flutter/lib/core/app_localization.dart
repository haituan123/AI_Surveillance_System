import 'package:flutter/widgets.dart';

import 'app_settings.dart';

class AppTranslator {
  const AppTranslator._();

  static const Map<String, String> _englishToVietnamese = {
    'Settings': 'Cài đặt',
    'Language': 'Ngôn ngữ',
    'English': 'Tiếng Anh',
    'Vietnamese': 'Tiếng Việt',
    'Appearance': 'Giao diện',
    'Light': 'Sáng',
    'Dark': 'Tối',
    'Close': 'Đóng',
    'Dashboard': 'Tổng quan',
    'Members': 'Thành viên',
    'Register': 'Đăng ký',
    'Surveillance': 'Giám sát',
    'Video QA': 'Hỏi đáp video',
    'Logs': 'Nhật ký',
    'AI Face Security': 'An ninh nhận diện khuôn mặt AI',
    'Operational Overview': 'Tổng quan vận hành',
    'Monitor backend health, camera activity, recognition coverage, and recent alert activity.':
        'Theo dõi trạng thái máy chủ, camera, nhận diện và các cảnh báo gần đây.',
    'System status': 'Trạng thái hệ thống',
    'Backend online': 'Máy chủ trực tuyến',
    'Backend offline': 'Máy chủ ngoại tuyến',
    'Backend checking': 'Đang kiểm tra máy chủ',
    'Camera status': 'Trạng thái camera',
    'Stopped': 'Đã dừng',
    'Registered people': 'Người đã đăng ký',
    'Unread alerts': 'Cảnh báo chưa đọc',
    'Latest detection': 'Phát hiện mới nhất',
    'Recent alerts': 'Cảnh báo gần đây',
    'No persistent live detection yet':
        'Chưa có phát hiện trực tiếp nào được lưu',
    'Uploaded-video results are temporary and do not appear here.':
        'Kết quả video tải lên chỉ là tạm thời và không xuất hiện tại đây.',
    'No recent alerts': 'Không có cảnh báo gần đây',
    'Unknown-person alerts from live mode will appear here.':
        'Cảnh báo người lạ từ chế độ trực tiếp sẽ xuất hiện tại đây.',
    'Open logs': 'Mở nhật ký',
    'View logs': 'Xem nhật ký',
    'Retry': 'Thử lại',
    'Review registered people and manage saved face images.':
        'Xem người đã đăng ký và quản lý ảnh khuôn mặt đã lưu.',
    'Loading members': 'Đang tải thành viên',
    'Fetching registered people from the backend.':
        'Đang tải danh sách người đã đăng ký từ máy chủ.',
    'Could not load members': 'Không thể tải thành viên',
    'Search members': 'Tìm thành viên',
    'Clear search': 'Xóa tìm kiếm',
    'No registered people': 'Chưa có người đăng ký',
    'Registered people will appear here after image registration.':
        'Người đã đăng ký sẽ xuất hiện tại đây sau khi đăng ký ảnh.',
    'No matching members': 'Không có thành viên phù hợp',
    'No registered person matches the current search filter.':
        'Không có người đăng ký nào khớp với bộ lọc hiện tại.',
    'Delete member': 'Xóa thành viên',
    'Cancel': 'Hủy',
    'Delete': 'Xóa',
    'Unknown date': 'Không rõ ngày',
    'Unknown error': 'Lỗi không xác định',
    'Add known people using clear face images.':
        'Thêm người quen bằng ảnh khuôn mặt rõ nét.',
    'Person details': 'Thông tin cá nhân',
    'Person name': 'Tên người',
    'Enter the name used in alerts and logs':
        'Nhập tên dùng trong cảnh báo và nhật ký',
    'Face images': 'Ảnh khuôn mặt',
    'Choose face images': 'Chọn ảnh khuôn mặt',
    'Replace images': 'Thay ảnh',
    'No images selected': 'Chưa chọn ảnh',
    'Use clear JPG, PNG, or WebP images with one visible face per photo.':
        'Dùng ảnh JPG, PNG hoặc WebP rõ nét, mỗi ảnh chỉ có một khuôn mặt.',
    'Clear selection': 'Bỏ lựa chọn',
    'Remove image': 'Xóa ảnh',
    'Enter a person name and choose at least one face image.':
        'Nhập tên và chọn ít nhất một ảnh khuôn mặt.',
    'Enter a person name first.': 'Hãy nhập tên trước.',
    'Choose at least one face image.': 'Hãy chọn ít nhất một ảnh khuôn mặt.',
    'Registering...': 'Đang đăng ký...',
    'Monitor the live webcam or analyze a temporary uploaded video.':
        'Theo dõi webcam trực tiếp hoặc phân tích video tải lên tạm thời.',
    'Live webcam': 'Webcam trực tiếp',
    'Upload video': 'Tải video lên',
    'Upload Video': 'Tải video lên',
    'Camera controls': 'Điều khiển camera',
    'Camera': 'Camera',
    'No camera configured': 'Chưa cấu hình camera',
    'Add the laptop webcam before starting live surveillance.':
        'Thêm webcam máy tính trước khi bắt đầu giám sát trực tiếp.',
    'Add laptop webcam': 'Thêm webcam máy tính',
    'Start': 'Bắt đầu',
    'Stop': 'Dừng',
    'Camera preview': 'Xem trước camera',
    'Video preview': 'Xem trước video',
    'Camera unavailable': 'Camera không khả dụng',
    'Retry camera': 'Thử lại camera',
    'Backend unavailable': 'Máy chủ không khả dụng',
    'Check the backend connection and retry.':
        'Kiểm tra kết nối máy chủ và thử lại.',
    'Camera stopped': 'Camera đã dừng',
    'Start surveillance to show the live camera feed.':
        'Bắt đầu giám sát để hiển thị hình ảnh trực tiếp.',
    'No video selected': 'Chưa chọn video',
    'Choose a video to begin temporary analysis.':
        'Chọn video để bắt đầu phân tích tạm thời.',
    'Preparing preview': 'Đang chuẩn bị xem trước',
    'Frames will appear as the uploaded video is processed.':
        'Khung hình sẽ xuất hiện khi video tải lên được xử lý.',
    'Waiting for frame': 'Đang chờ khung hình',
    'A preview frame will appear when analysis produces one.':
        'Khung hình xem trước sẽ xuất hiện khi có kết quả phân tích.',
    'Temporary mode: events and frames are not saved to history.':
        'Chế độ tạm thời: sự kiện và khung hình không được lưu vào lịch sử.',
    'Choose video': 'Chọn video',
    'Cancel analysis': 'Hủy phân tích',
    'Clear result': 'Xóa kết quả',
    'No video': 'Không có video',
    'Last detection': 'Phát hiện gần nhất',
    'No live detection result': 'Chưa có kết quả phát hiện trực tiếp',
    'Start the camera to see recognized and unknown people.':
        'Bật camera để xem người quen và người lạ.',
    'Known person': 'Người quen',
    'Unknown Person': 'Người lạ',
    'Unknown person': 'Người lạ',
    'Restricted area': 'Vùng cấm',
    'Loitering': 'Lảng vảng',
    'Knife / sharp weapon': 'Cầm dao / Vũ khí nhọn',
    'Dangerous weapon': 'Vũ khí nguy hiểm',
    'Fire / smoke': 'Cháy nổ / Khói',
    'Theft': 'Lấy trộm đồ vật',
    'Violence': 'Hành vi bạo lực',
    'Security alert': 'Cảnh báo an ninh',
    'queued': 'đang chờ',
    'running': 'đang chạy',
    'completed': 'đã hoàn tất',
    'failed': 'thất bại',
    'cancelled': 'đã hủy',
    'unknown person': 'người lạ',
    'restricted area': 'khu vực hạn chế',
    'Unknown person entered ': 'Người lạ đã vào ',
    ' lingering around ': ' đang lảng vảng quanh ',
    ' lingering around a restricted area':
        ' đang lảng vảng quanh khu vực hạn chế',
    'Restricted zones': 'Khu vực hạn chế',
    'Tap the live preview to place 4 corner points. Unknown people inside an active zone briefly will alert.':
        'Chạm vào hình ảnh trực tiếp để đặt 4 điểm góc. Người lạ ở trong vùng hoạt động sẽ kích hoạt cảnh báo.',
    'Zone name': 'Tên khu vực',
    'Server door': 'Cửa phòng máy chủ',
    'Undo': 'Hoàn tác',
    'Clear': 'Xóa',
    'Delete zone': 'Xóa khu vực',
    'Temporary events': 'Sự kiện tạm thời',
    'No temporary events': 'Không có sự kiện tạm thời',
    'Choose a video to show analysis events here.':
        'Chọn video để hiển thị sự kiện phân tích tại đây.',
    'Permission needed': 'Cần cấp quyền',
    'Request failed': 'Yêu cầu thất bại',
    'Dismiss': 'Bỏ qua',
    'Persistent Logs & Alerts': 'Nhật ký và cảnh báo đã lưu',
    'Only live-webcam events are saved. Uploaded-video events never appear here.':
        'Chỉ sự kiện webcam trực tiếp được lưu. Sự kiện video tải lên không xuất hiện tại đây.',
    'Detection logs': 'Nhật ký phát hiện',
    'Alerts': 'Cảnh báo',
    'Live detection history': 'Lịch sử phát hiện trực tiếp',
    'Alert inbox': 'Hộp thư cảnh báo',
    'Delete all logs': 'Xóa toàn bộ nhật ký',
    'Delete all alerts': 'Xóa toàn bộ cảnh báo',
    'No live detection logs': 'Không có nhật ký phát hiện trực tiếp',
    'Start live surveillance to create history.':
        'Bắt đầu giám sát trực tiếp để tạo lịch sử.',
    'No persistent alerts': 'Không có cảnh báo đã lưu',
    'Confirmed unknown people from live mode appear here.':
        'Người lạ được xác nhận trong chế độ trực tiếp sẽ xuất hiện tại đây.',
    'Mark read': 'Đánh dấu đã đọc',
    'Mark unread': 'Đánh dấu chưa đọc',
    'Delete selected': 'Xóa mục đã chọn',
    'Deleting': 'Đang xóa',
    'Loading alerts': 'Đang tải cảnh báo',
    'Loading detection logs': 'Đang tải nhật ký phát hiện',
    'Could not load logs': 'Không thể tải nhật ký',
    'Security Video Q&A Assistant': 'Trợ lý Hỏi - Đáp Video Giám Sát (CCTV QA)',
    'Natural-language surveillance questions • Weapons, theft, clothing colors & timestamps':
        'Hỗ trợ hỏi đáp tự nhiên • Suy luận vũ khí, trộm cắp, màu áo và mốc thời gian',
    'New conversation': 'Phiên mới',
    'New conversation (': 'Hỏi đáp mới (',
    'Conversation': 'Phiên hỏi đáp',
    'Data scope: ': 'Phạm vi dữ liệu: ',
    'Uploading...': 'Đang tải lên...',
    'All cameras & videos': 'Tất cả camera và video',
    'Live webcam stream': 'Webcam trực tiếp',
    'Conversation history': 'Lịch sử phiên hỏi đáp',
    'Refresh': 'Làm mới',
    'No conversations yet': 'Chưa có phiên hỏi đáp nào',
    'Delete this conversation': 'Xóa phiên này',
    'Start asking questions about surveillance footage':
        'Bắt đầu đặt câu hỏi về dữ liệu camera giám sát',
    'Examples: “Did anyone take a backpack?”, “Is anyone holding a knife?”, “Who is wearing red?”':
        'Ví dụ: “Có ai lấy balo không?”, “Có người nào cầm dao không?”, “Ai mặc áo đỏ?”',
    'Translation & AI reasoning': 'Bản dịch và suy luận AI',
    'Verified evidence (clips & timestamps):':
        'Bằng chứng xác thực (đoạn video và mốc thời gian):',
    'Ask a question about the surveillance video...':
        'Nhập câu hỏi về video giám sát...',
    'DANGER / WEAPON ALERT': 'CẢNH BÁO NGUY HIỂM / VŨ KHÍ',
    'OBJECT & THEFT REASONING': 'SUY LUẬN ĐỒ VẬT & TRỘM CẮP',
    'CLOTHING & ACCESSORY RECOGNITION': 'NHẬN DẠNG MÀU ÁO VÀ PHỤ KIỆN',
    'KNOWN / UNKNOWN RECOGNITION': 'NHẬN DẠNG QUEN / LẠ',
    'PEOPLE COUNT': 'ĐẾM SỐ LƯỢNG NGƯỜI',
    'TIMELINE LOCATION': 'ĐỊNH VỊ MỐC THỜI GIAN',
    'SECURITY Q&A': 'HỎI ĐÁP AN NINH',
    'Delete conversation?': 'Xác nhận xóa phiên hỏi đáp',
    'Deleting this conversation also removes all messages, uploaded videos, and analyzed AI data.':
        'Xóa phiên hỏi đáp này sẽ đồng thời xóa toàn bộ tin nhắn, video đã tải lên và dữ liệu AI đã phân tích.',
    'Delete video?': 'Xác nhận xóa video',
    'Retry analysis': 'Thử lại',
    'Video processing failed': 'Video xử lý thất bại',
    'Delete video and related data': 'Xóa video và dữ liệu liên quan',
    'Live surveillance started.': 'Đã bắt đầu giám sát trực tiếp.',
    'Live surveillance stopped.': 'Đã dừng giám sát trực tiếp.',
    'Laptop webcam added.': 'Đã thêm webcam máy tính.',
    'Restricted zone saved.': 'Đã lưu khu vực hạn chế.',
    'Restricted zone deleted.': 'Đã xóa khu vực hạn chế.',
    'Video analysis submitted.': 'Đã gửi video để phân tích.',
    'Video analysis cleared.': 'Đã xóa kết quả phân tích video.',
    'Alert marked read.': 'Đã đánh dấu cảnh báo là đã đọc.',
    'Alert marked unread.': 'Đã đánh dấu cảnh báo là chưa đọc.',
    'Permission denied. Allow camera/file access and try again.':
        'Quyền truy cập bị từ chối. Hãy cấp quyền camera/tệp rồi thử lại.',
    'Backend unavailable. Check that the backend server is running.':
        'Máy chủ không khả dụng. Hãy kiểm tra máy chủ đang chạy.',
    'Registered ': 'Đăng ký lúc ',
    ' accepted': ' ảnh hợp lệ',
    ' rejected': ' ảnh bị từ chối',
    ' active': ' đang hoạt động',
    ' inactive': ' không hoạt động',
    ' points': ' điểm',
    ' frames': ' khung hình',
    ' known': ' người quen',
    ' unknown': ' người lạ',
    ' detected': ' được phát hiện',
    ' image': ' ảnh',
    ' images': ' ảnh',
  };

  static String translate(String value, AppLanguage language) {
    if (value.isEmpty) return value;
    final phrases = language == AppLanguage.vietnamese
        ? _englishToVietnamese
        : _vietnameseToEnglish;
    if (phrases.containsKey(value)) return phrases[value]!;
    var translated = value;
    final entries = language == AppLanguage.vietnamese
        ? _englishPhrasesByLength
        : _vietnamesePhrasesByLength;
    for (final entry in entries) {
      if (translated.contains(entry.key)) {
        translated = translated.replaceAll(entry.key, entry.value);
      }
    }
    return translated;
  }

  static const Map<String, String> _legacyVietnameseToEnglish = {
    'Trợ lý Hỏi - Đáp Video Giám Sát (CCTV QA)': 'Security Video Q&A Assistant',
    'Phiên hỏi đáp': 'Conversation',
    'Hỏi đáp mới (': 'New conversation (',
    'Hỗ trợ hỏi đáp tự nhiên tiếng Việt • Suy luận vũ khí, trộm cắp, màu áo & mốc thời gian':
        'Natural-language surveillance questions • Weapons, theft, clothing colors & timestamps',
    'Phiên mới': 'New conversation',
    'Phạm vi dữ liệu: ': 'Data scope: ',
    'Đang tải lên...': 'Uploading...',
    'Tất cả Camera & Video': 'All cameras & videos',
    'Webcam Live Stream': 'Live webcam stream',
    'Lịch sử phiên hỏi đáp': 'Conversation history',
    'Làm mới': 'Refresh',
    'Chưa có phiên hỏi đáp nào': 'No conversations yet',
    'Xóa phiên này': 'Delete this conversation',
    'Bắt đầu đặt câu hỏi về dữ liệu camera giám sát':
        'Start asking questions about surveillance footage',
    'Ví dụ: "Có ai lấy balo không?", "Có người nào cầm dao không?", "Ai mặc áo đỏ?"':
        'Examples: “Did anyone take a backpack?”, “Is anyone holding a knife?”, “Who is wearing red?”',
    'Bản dịch & Suy luận AI (Reasoning EN)': 'Translation & AI reasoning',
    'Bằng chứng xác thực (Evidence Clips & Timestamps):':
        'Verified evidence (clips & timestamps):',
    'Nhập câu hỏi bằng tiếng Việt về video camera (VD: Có ai lấy balo không?)...':
        'Ask a question about the surveillance video...',
    'CẢNH BÁO NGUY HIỂM / VŨ KHÍ': 'DANGER / WEAPON ALERT',
    'SUY LUẬN ĐỒ VẬT & TRỘM CẮP': 'OBJECT & THEFT REASONING',
    'NHẬN DẠNG MÀU ÁO & PHỤ KIỆN': 'CLOTHING & ACCESSORY RECOGNITION',
    'NHẬN DẠNG QUEN / LẠ': 'KNOWN / UNKNOWN RECOGNITION',
    'ĐẾM SỐ LƯỢNG NGƯỜI': 'PEOPLE COUNT',
    'ĐỊNH VỊ MỐC THỜI GIAN': 'TIMELINE LOCATION',
    'HỎI ĐÁP AN NINH': 'SECURITY Q&A',
    'Xác nhận xóa phiên hỏi đáp': 'Delete conversation?',
    'Xóa phiên hỏi đáp này sẽ đồng thời xóa toàn bộ tin nhắn, video đã tải lên và dữ liệu AI đã phân tích của phiên.':
        'Deleting this conversation also removes all messages, uploaded videos, and analyzed AI data.',
    'Xác nhận xóa video': 'Delete video?',
    'Hủy': 'Cancel',
    'Xóa': 'Delete',
    'Đóng': 'Close',
    'Thử lại': 'Retry analysis',
    'Video bị lỗi khi xử lý': 'Video processing failed',
    'Xóa video và dữ liệu liên quan': 'Delete video and related data',
    'Mốc: ': 'Time: ',
    ' tin nhắn': ' messages',
    'Đang chuẩn bị xử lý...': 'Preparing analysis...',
    'Đang phân tích: ': 'Analyzing: ',
    'Đã hoàn tất phân tích': 'Analysis completed',
    'Xử lý thất bại: ': 'Processing failed: ',
    'Không xác định': 'Unknown',
    'Lỗi không xác định': 'Unknown error',
    'Không thể tải lịch sử hỏi đáp: ': 'Could not load conversation history: ',
    'Không thể tải tin nhắn: ': 'Could not load messages: ',
    'Lỗi tạo phiên hỏi đáp: ': 'Could not create conversation: ',
    'Không thể xóa: ': 'Could not delete: ',
    'Lỗi tải video lên: ': 'Video upload failed: ',
    'Lỗi xóa video: ': 'Could not delete video: ',
    'Không thể thử lại: ': 'Could not retry: ',
    'Lỗi truy vấn AI: ': 'AI query failed: ',
    'Yêu cầu thất bại': 'Request failed',
    'Phát hiện người trong khu vực ': 'Person detected in restricted area ',
    'Phát hiện người lảng vảng tại ': 'Person loitering at ',
    'Người lạ': 'Unknown person',
    'Vùng cấm': 'Restricted area',
    'Lảng vảng': 'Loitering',
    'Cầm dao / Vũ khí nhọn': 'Knife / sharp weapon',
    'Vũ khí nguy hiểm': 'Dangerous weapon',
    'Cháy nổ / Khói': 'Fire / smoke',
    'Lấy trộm đồ vật': 'Theft',
    'Hành vi bạo lực': 'Violence',
    'Cảnh báo an ninh': 'Security alert',
    'Đã xóa phiên hỏi đáp và dữ liệu video liên quan':
        'Conversation and related video data deleted.',
    'Đã tải video lên. AI đang bắt đầu xử lý và lập chỉ mục frames...':
        'Video uploaded. AI is starting analysis and frame indexing...',
    'Đang bắt đầu xử lý lại video ': 'Restarting analysis for video ',
    'Đã xóa video ': 'Deleted video ',
    ' và các dữ liệu liên quan': ' and related data',
    'Query EN: ': 'English query: ',
    'Reasoning: ': 'Reasoning: ',
    'Có ai cầm dao hoặc hành vi nguy hiểm không?':
        'Is anyone holding a knife or behaving dangerously?',
    'Có ai để quên đồ vật nào không?': 'Did anyone leave an object behind?',
    'Có bao nhiêu người xuất hiện trong khung hình?':
        'How many people appear in the frame?',
    'Người mặc áo đen hoặc áo đỏ xuất hiện lúc mấy giờ?':
        'When did the person wearing black or red appear?',
    'Trong video có ai lấy chiếc balo trên bàn không?':
        'Did anyone take the backpack from the table?',
  };

  static final Map<String, String> _vietnameseToEnglish = {
    for (final entry in _englishToVietnamese.entries) entry.value: entry.key,
    ..._legacyVietnameseToEnglish,
  };

  static final List<MapEntry<String, String>> _englishPhrasesByLength =
      _sortedPhrases(_englishToVietnamese);
  static final List<MapEntry<String, String>> _vietnamesePhrasesByLength =
      _sortedPhrases(_vietnameseToEnglish);

  static List<MapEntry<String, String>> _sortedPhrases(
    Map<String, String> phrases,
  ) =>
      phrases.entries.toList()
        ..sort((a, b) => b.key.length.compareTo(a.key.length));
}

extension AppLocalizationContext on BuildContext {
  String tr(String value) =>
      AppTranslator.translate(value, appSettings.language);
}
