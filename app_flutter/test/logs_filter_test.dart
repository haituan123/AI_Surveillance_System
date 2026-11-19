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

  SecurityEventModel event(String type, {String? label}) => SecurityEventModel(
        id: type.hashCode,
        sourceId: 'qa-video',
        sourceType: 'qa_video',
        sourceName: 'incident.mp4',
        eventType: type,
        startTimestamp: 2,
        endTimestamp: 4,
        confidence: 0.88,
        detectedLabel: label,
        status: 'open',
        createdAt: '2026-11-18T08:01:00',
      );

  test('person filters distinguish known and unknown detections', () {
    expect(LiveDetectionFilter.all.matches(knownLog), isTrue);
    expect(LiveDetectionFilter.known.matches(knownLog), isTrue);
    expect(LiveDetectionFilter.known.matches(unknownLog), isFalse);
    expect(LiveDetectionFilter.unknown.matches(unknownLog), isTrue);
  });

  test('live alert filters are limited to live alert categories', () {
    expect(
      LiveAlertFilter.unknownPerson.matches(
        alert('unknown_person', 'Unknown person detected'),
      ),
      isTrue,
    );
    expect(
      LiveAlertFilter.restrictedArea.matches(
        alert('restricted_area', 'Restricted area entered'),
      ),
      isTrue,
    );
    expect(
      LiveAlertFilter.loitering.matches(alert('loitering', 'Loitering')),
      isTrue,
    );
    expect(
      LiveAlertFilter.unknownPerson.matches(
        alert('restricted_area', 'Unknown person in restricted area'),
      ),
      isFalse,
    );
  });

  test('investigation filters recognize only incident categories', () {
    expect(
      InvestigationIncidentFilter.violenceFighting.matches(event('fighting')),
      isTrue,
    );
    expect(
      InvestigationIncidentFilter.fireSmoke.matches(
        event('object_present', label: 'fire'),
      ),
      isTrue,
    );
    expect(
      InvestigationIncidentFilter.weapons.matches(
        event('object_present', label: 'knife'),
      ),
      isTrue,
    );
    expect(
      InvestigationIncidentFilter.theftRobbery.matches(event('theft')),
      isTrue,
    );
    expect(
      InvestigationIncidentFilter.weapons.matches(event('fighting')),
      isFalse,
    );
  });
}
