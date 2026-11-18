import 'package:app_flutter/models/security_models.dart';
import 'package:app_flutter/screens/logs_screen.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  const knownLog = DetectionLogModel(
    id: 1,
    sessionId: 1,
    status: 'known',
    cameraName: 'Front door',
    detectedAt: '2026-11-18T08:00:00',
    memberName: 'Alice',
  );
  const unknownLog = DetectionLogModel(
    id: 2,
    sessionId: 1,
    status: 'unknown',
    cameraName: 'Front door',
    detectedAt: '2026-11-18T08:01:00',
  );

  AlertModel alert(String type, String message) => AlertModel(
    id: type.hashCode,
    detectionLogId: unknownLog.id,
    alertType: type,
    message: message,
    cameraName: 'Front door',
    isRead: false,
    createdAt: '2026-11-18T08:01:00',
  );

  test('person filters distinguish known and unknown detections', () {
    expect(SecurityRecordFilter.knownPerson.matchesLog(knownLog), isTrue);
    expect(SecurityRecordFilter.knownPerson.matchesLog(unknownLog), isFalse);
    expect(SecurityRecordFilter.unknownPerson.matchesLog(unknownLog), isTrue);
    expect(
      SecurityRecordFilter.unknownPerson.matchesAlert(
        alert('fire_smoke', 'Fire detected'),
      ),
      isFalse,
    );
  });

  test('threat filters recognize requested alert categories', () {
    expect(
      SecurityRecordFilter.fighting.matchesAlert(
        alert('violence', 'Fighting detected'),
      ),
      isTrue,
    );
    expect(
      SecurityRecordFilter.fireSmoke.matchesAlert(
        alert('fire_smoke', 'Fire and smoke detected'),
      ),
      isTrue,
    );
    expect(
      SecurityRecordFilter.shooting.matchesAlert(
        alert('weapon_drawn', 'Gun shooting detected'),
      ),
      isTrue,
    );
    expect(
      SecurityRecordFilter.robberyTheft.matchesAlert(
        alert('theft', 'Robbery detected'),
      ),
      isTrue,
    );
  });

  test('linked threat alerts make their detection logs filterable', () {
    final fightingAlert = alert('violence', 'Fight detected');
    expect(
      SecurityRecordFilter.fighting.matchesLog(
        unknownLog,
        linkedAlerts: [fightingAlert],
      ),
      isTrue,
    );
    expect(
      SecurityRecordFilter.fireSmoke.matchesLog(
        unknownLog,
        linkedAlerts: [fightingAlert],
      ),
      isFalse,
    );
  });
}
