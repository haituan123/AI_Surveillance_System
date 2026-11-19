import 'dart:async';

import 'package:flutter/material.dart' hide Text;

import '../core/app_localization.dart';
import '../core/timestamp_formatter.dart';
import '../models/security_models.dart';
import '../services/security_service.dart';
import '../theme/app_tokens.dart';
import '../widgets/app_message.dart';
import '../widgets/app_page.dart';
import '../widgets/empty_panel.dart';
import '../widgets/header_block.dart';
import '../widgets/localized_text.dart';

class LogsScreen extends StatefulWidget {
  const LogsScreen({super.key, this.service});

  final SecurityService? service;

  @override
  State<LogsScreen> createState() => _LogsScreenState();
}

enum SecurityRecordFilter {
  knownPerson,
  unknownPerson,
  fighting,
  fireSmoke,
  shooting,
  robberyTheft,
}

extension SecurityRecordFilterDetails on SecurityRecordFilter {
  String get label => switch (this) {
    SecurityRecordFilter.knownPerson => 'Known person',
    SecurityRecordFilter.unknownPerson => 'Unknown person',
    SecurityRecordFilter.fighting => 'Fighting',
    SecurityRecordFilter.fireSmoke => 'Fire / smoke',
    SecurityRecordFilter.shooting => 'Weapon / shooting',
    SecurityRecordFilter.robberyTheft => 'Robbery / theft',
  };

  IconData get icon => switch (this) {
    SecurityRecordFilter.knownPerson => Icons.verified_user_outlined,
    SecurityRecordFilter.unknownPerson => Icons.person_search_outlined,
    SecurityRecordFilter.fighting => Icons.sports_mma_outlined,
    SecurityRecordFilter.fireSmoke => Icons.local_fire_department_outlined,
    SecurityRecordFilter.shooting => Icons.gps_fixed,
    SecurityRecordFilter.robberyTheft => Icons.front_hand_outlined,
  };

  Color get accentColor => switch (this) {
    SecurityRecordFilter.knownPerson => AppColors.success,
    SecurityRecordFilter.unknownPerson => AppColors.warning,
    SecurityRecordFilter.fighting => AppColors.danger,
    SecurityRecordFilter.fireSmoke => Colors.deepOrange,
    SecurityRecordFilter.shooting => Colors.deepPurple,
    SecurityRecordFilter.robberyTheft => Colors.brown,
  };

  bool matchesLog(
    DetectionLogModel log, {
    Iterable<AlertModel> linkedAlerts = const [],
  }) {
    return switch (this) {
      SecurityRecordFilter.knownPerson => log.status == 'known',
      SecurityRecordFilter.unknownPerson => log.status != 'known',
      _ => linkedAlerts.any(matchesAlert),
    };
  }

  bool matchesAlert(AlertModel alert, {DetectionLogModel? linkedLog}) {
    final type = alert.alertType.toLowerCase();
    final message = alert.message.toLowerCase();
    return switch (this) {
      SecurityRecordFilter.knownPerson => linkedLog?.status == 'known',
      SecurityRecordFilter.unknownPerson =>
        (linkedLog != null && linkedLog.status != 'known') ||
            type == 'unknown_person' ||
            type == 'restricted_area' ||
            type == 'loitering' ||
            message.contains('unknown person'),
      SecurityRecordFilter.fighting =>
        type == 'violence' ||
            type == 'fighting' ||
            message.contains('fight') ||
            message.contains('violence') ||
            message.contains('đánh nhau'),
      SecurityRecordFilter.fireSmoke =>
        type == 'fire_smoke' ||
            message.contains('fire') ||
            message.contains('smoke') ||
            message.contains('explosion') ||
            message.contains('cháy') ||
            message.contains('nổ'),
      SecurityRecordFilter.shooting =>
        type == 'shooting' ||
            type == 'weapon_drawn' ||
            type == 'weapon_present' ||
            type == 'knife_threat' ||
            type == 'knife_present' ||
            message.contains('shoot') ||
            message.contains('gun') ||
            message.contains('knife') ||
            message.contains('firearm') ||
            message.contains('bắn súng'),
      SecurityRecordFilter.robberyTheft =>
        type == 'theft' ||
            type.startsWith('robbery') ||
            message.contains('robbery') ||
            message.contains('theft') ||
            message.contains('stolen') ||
            message.contains('cướp') ||
            message.contains('trộm'),
    };
  }

  bool matchesEvent(SecurityEventModel event) {
    final type = event.eventType.toLowerCase();
    final label = event.detectedLabel?.toLowerCase() ?? '';
    return switch (this) {
      SecurityRecordFilter.knownPerson ||
      SecurityRecordFilter.unknownPerson => false,
      SecurityRecordFilter.fighting => type == 'fighting' || type == 'violence',
      SecurityRecordFilter.fireSmoke =>
        type == 'fire_smoke' || label == 'fire' || label == 'smoke',
      SecurityRecordFilter.shooting =>
        type == 'shooting' ||
            type == 'weapon_drawn' ||
            type == 'weapon_present' ||
            type == 'knife_threat' ||
            type == 'knife_present' ||
            const {
              'gun',
              'pistol',
              'rifle',
              'knife',
              'scissors',
            }.contains(label),
      SecurityRecordFilter.robberyTheft =>
        type == 'theft' ||
            type == 'possible_theft' ||
            type.startsWith('robbery'),
    };
  }
}

class _LogsScreenState extends State<LogsScreen> {
  late final SecurityService _service = widget.service ?? SecurityService();
  Timer? _refreshTimer;
  List<DetectionLogModel> _logs = const [];
  List<AlertModel> _alerts = const [];
  List<SecurityEventModel> _events = const [];
  Set<int> _selectedLogIds = const {};
  Set<int> _selectedAlertIds = const {};
  Set<SecurityRecordFilter> _activeFilters = const {};
  bool _loading = true;
  bool _deletingLogs = false;
  bool _deletingAlerts = false;
  bool _refreshInFlight = false;
  int _refreshFailures = 0;
  String? _error;

  bool get _busy => _loading || _deletingLogs || _deletingAlerts;

  List<DetectionLogModel> get _visibleLogs {
    if (_activeFilters.isEmpty) return _logs;
    return _logs.where((log) {
      final linkedAlerts = _alerts.where(
        (alert) => alert.detectionLogId == log.id,
      );
      return _activeFilters.any(
        (filter) => filter.matchesLog(log, linkedAlerts: linkedAlerts),
      );
    }).toList();
  }

  List<AlertModel> get _visibleAlerts {
    if (_activeFilters.isEmpty) return _alerts;
    return _alerts.where((alert) {
      DetectionLogModel? linkedLog;
      for (final log in _logs) {
        if (log.id == alert.detectionLogId) {
          linkedLog = log;
          break;
        }
      }
      return _activeFilters.any(
        (filter) => filter.matchesAlert(alert, linkedLog: linkedLog),
      );
    }).toList();
  }

  List<SecurityEventModel> get _visibleEvents {
    if (_activeFilters.isEmpty) return _events;
    return _events
        .where(
          (event) => _activeFilters.any((filter) => filter.matchesEvent(event)),
        )
        .toList();
  }

  void _toggleFilter(SecurityRecordFilter filter) {
    setState(() {
      final next = {..._activeFilters};
      if (!next.add(filter)) next.remove(filter);
      _activeFilters = next;
    });
  }

  @override
  void initState() {
    super.initState();
    _refresh();
    _refreshTimer = Timer.periodic(
      const Duration(seconds: 5),
      (_) => _refreshFromTimer(),
    );
  }

  @override
  void dispose() {
    _refreshTimer?.cancel();
    super.dispose();
  }

  Future<void> _refresh({bool background = false}) async {
    if (_refreshInFlight) return;
    _refreshInFlight = true;
    if (!background) {
      setState(() {
        _loading = true;
        _error = null;
      });
    }
    try {
      final values = await Future.wait([
        _service.listLogs(),
        _service.listAlerts(),
        _service.listSecurityEvents(),
      ]);
      if (!mounted) return;
      setState(() {
        _logs = values[0] as List<DetectionLogModel>;
        _alerts = values[1] as List<AlertModel>;
        _events = values[2] as List<SecurityEventModel>;
        _refreshFailures = 0;
        _error = null;
        _selectedLogIds = _selectedLogIds
            .where((id) => _logs.any((log) => log.id == id))
            .toSet();
        _selectedAlertIds = _selectedAlertIds
            .where((id) => _alerts.any((alert) => alert.id == id))
            .toSet();
      });
    } catch (error) {
      if (mounted) {
        _refreshFailures += 1;
        if (!background || _refreshFailures >= 3) {
          setState(() => _error = friendlyErrorMessage(error));
        }
      }
    } finally {
      _refreshInFlight = false;
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _refreshFromTimer() async {
    if (_busy || _selectedLogIds.isNotEmpty || _selectedAlertIds.isNotEmpty) {
      return;
    }
    await _refresh(background: true);
  }

  Future<void> _toggleRead(AlertModel alert) async {
    try {
      final updated = await _service.setAlertRead(alert.id, !alert.isRead);
      if (!mounted) return;
      setState(() {
        final index = _alerts.indexWhere((item) => item.id == alert.id);
        if (index >= 0) {
          _alerts = [..._alerts]..[index] = updated;
        }
      });
      showAppSnackBar(
        context,
        message: updated.isRead ? 'Alert marked read.' : 'Alert marked unread.',
        tone: AppMessageTone.success,
      );
    } catch (error) {
      if (mounted) setState(() => _error = friendlyErrorMessage(error));
    }
  }

  void _toggleLogSelection(DetectionLogModel log, bool selected) {
    setState(() {
      final selectedIds = {..._selectedLogIds};
      if (selected) {
        selectedIds.add(log.id);
      } else {
        selectedIds.remove(log.id);
      }
      _selectedLogIds = selectedIds;
    });
  }

  void _toggleAlertSelection(AlertModel alert, bool selected) {
    setState(() {
      final selectedIds = {..._selectedAlertIds};
      if (selected) {
        selectedIds.add(alert.id);
      } else {
        selectedIds.remove(alert.id);
      }
      _selectedAlertIds = selectedIds;
    });
  }

  Future<bool> _confirmDelete({
    required String title,
    required String message,
  }) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        icon: Icon(Icons.delete_outline, color: AppColors.danger),
        title: Text(title),
        content: Text(message),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: Text('Cancel'),
          ),
          FilledButton.icon(
            style: FilledButton.styleFrom(
              backgroundColor: AppColors.danger,
              foregroundColor: Colors.white,
            ),
            onPressed: () => Navigator.of(context).pop(true),
            icon: Icon(Icons.delete_outline),
            label: Text('Delete'),
          ),
        ],
      ),
    );
    return confirmed == true;
  }

  Future<void> _deleteSelectedLogs() async {
    final count = _selectedLogIds.length;
    if (count == 0 || _deletingLogs) return;

    final confirmed = await _confirmDelete(
      title: count == 1 ? 'Delete log' : 'Delete logs',
      message: count == 1
          ? 'Delete this detection log from persistent storage?'
          : 'Delete these $count detection logs from persistent storage?',
    );
    if (confirmed != true) return;

    final ids = _selectedLogIds.toList();
    setState(() {
      _deletingLogs = true;
      _error = null;
    });
    try {
      await Future.wait(ids.map(_service.deleteLog));
      if (!mounted) return;
      setState(() => _selectedLogIds = const {});
      await _refresh();
      if (!mounted) return;
      showAppSnackBar(
        context,
        message: count == 1 ? 'Deleted selected log.' : 'Deleted $count logs.',
        tone: AppMessageTone.success,
      );
    } catch (error) {
      if (mounted) setState(() => _error = friendlyErrorMessage(error));
    } finally {
      if (mounted) setState(() => _deletingLogs = false);
    }
  }

  Future<void> _deleteSelectedAlerts() async {
    final count = _selectedAlertIds.length;
    if (count == 0 || _deletingAlerts) return;

    final confirmed = await _confirmDelete(
      title: count == 1 ? 'Delete alert' : 'Delete alerts',
      message: count == 1
          ? 'Delete this alert from persistent storage?'
          : 'Delete these $count alerts from persistent storage?',
    );
    if (confirmed != true) return;

    final ids = _selectedAlertIds.toList();
    setState(() {
      _deletingAlerts = true;
      _error = null;
    });
    try {
      await Future.wait(ids.map(_service.deleteAlert));
      if (!mounted) return;
      setState(() => _selectedAlertIds = const {});
      await _refresh();
      if (!mounted) return;
      showAppSnackBar(
        context,
        message: count == 1
            ? 'Deleted selected alert.'
            : 'Deleted $count alerts.',
        tone: AppMessageTone.success,
      );
    } catch (error) {
      if (mounted) setState(() => _error = friendlyErrorMessage(error));
    } finally {
      if (mounted) setState(() => _deletingAlerts = false);
    }
  }

  Future<void> _deleteAllLogs() async {
    if (_logs.isEmpty || _deletingLogs) return;
    final confirmed = await _confirmDelete(
      title: 'Delete all logs',
      message: 'Delete all detection logs from persistent storage?',
    );
    if (!confirmed) return;

    setState(() {
      _deletingLogs = true;
      _error = null;
    });
    try {
      await _service.deleteAllLogs();
      if (!mounted) return;
      setState(() => _selectedLogIds = const {});
      await _refresh();
      if (!mounted) return;
      showAppSnackBar(
        context,
        message: 'Deleted all logs.',
        tone: AppMessageTone.success,
      );
    } catch (error) {
      if (mounted) setState(() => _error = friendlyErrorMessage(error));
    } finally {
      if (mounted) setState(() => _deletingLogs = false);
    }
  }

  Future<void> _deleteAllAlerts() async {
    if (_alerts.isEmpty || _deletingAlerts) return;
    final confirmed = await _confirmDelete(
      title: 'Delete all alerts',
      message: 'Delete all alerts from persistent storage?',
    );
    if (!confirmed) return;

    setState(() {
      _deletingAlerts = true;
      _error = null;
    });
    try {
      await _service.deleteAllAlerts();
      if (!mounted) return;
      setState(() => _selectedAlertIds = const {});
      await _refresh();
      if (!mounted) return;
      showAppSnackBar(
        context,
        message: 'Deleted all alerts.',
        tone: AppMessageTone.success,
      );
    } catch (error) {
      if (mounted) setState(() => _error = friendlyErrorMessage(error));
    } finally {
      if (mounted) setState(() => _deletingAlerts = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final listHeight = (MediaQuery.sizeOf(context).height - 400)
        .clamp(360.0, 700.0)
        .toDouble();
    final unknownLabels = _UnknownPersonLabels(logs: _logs, alerts: _alerts);
    final visibleLogs = _visibleLogs;
    final visibleAlerts = _visibleAlerts;
    final visibleEvents = _visibleEvents;
    final records = _UnifiedSecurityRecord.merge(
      logs: visibleLogs,
      alerts: visibleAlerts,
      events: visibleEvents,
    );

    return AppPage(
      maxWidth: AppLayout.dataMaxWidth,
      children: [
        HeaderBlock(
          title: 'Persistent Logs & Alerts',
          subtitle:
              'Review live detections, alerts, and indexed security events in one place.',
          icon: Icons.receipt_long,
        ),
        const SizedBox(height: AppSpacing.md),
        if (_error != null)
          _ErrorPanel(message: _error!, onRetry: _busy ? null : _refresh),
        if (_error != null) const SizedBox(height: AppSpacing.md),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(AppSpacing.md),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                _RecordSummary(
                  logCount: visibleLogs.length,
                  alertCount: visibleAlerts.length,
                  eventCount: visibleEvents.length,
                ),
                if (_loading) const LinearProgressIndicator(),
                const SizedBox(height: AppSpacing.sm),
                _SecurityFilterBar(
                  selected: _activeFilters,
                  visibleLogCount: visibleLogs.length,
                  totalLogCount: _logs.length,
                  visibleAlertCount: visibleAlerts.length,
                  totalAlertCount: _alerts.length,
                  visibleEventCount: visibleEvents.length,
                  totalEventCount: _events.length,
                  onToggle: _toggleFilter,
                  onClear: () => setState(() => _activeFilters = const {}),
                ),
                if (_selectedLogIds.isNotEmpty) ...[
                  const SizedBox(height: AppSpacing.md),
                  _SelectionToolbar(
                    label: '${_selectedLogIds.length} log selected',
                    deleting: _deletingLogs,
                    onClear: () => setState(() => _selectedLogIds = const {}),
                    onDelete: _deleteSelectedLogs,
                  ),
                ],
                if (_selectedAlertIds.isNotEmpty) ...[
                  const SizedBox(height: AppSpacing.md),
                  _SelectionToolbar(
                    label: '${_selectedAlertIds.length} alert selected',
                    deleting: _deletingAlerts,
                    onClear: () => setState(() => _selectedAlertIds = const {}),
                    onDelete: _deleteSelectedAlerts,
                  ),
                ],
                const SizedBox(height: AppSpacing.md),
                SizedBox(
                  height: listHeight,
                  child: _UnifiedRecordsFeed(
                    records: records,
                    filtered: _activeFilters.isNotEmpty,
                    unknownLabels: unknownLabels,
                    loading: _loading,
                    deletingLogs: _deletingLogs,
                    deletingAlerts: _deletingAlerts,
                    selectedLogIds: _selectedLogIds,
                    selectedAlertIds: _selectedAlertIds,
                    onToggleLogSelection: _toggleLogSelection,
                    onToggleAlertSelection: _toggleAlertSelection,
                    onToggleAlertRead: _toggleRead,
                    onDeleteAllLogs: _deleteAllLogs,
                    onDeleteAllAlerts: _deleteAllAlerts,
                    totalLogCount: _logs.length,
                    totalAlertCount: _alerts.length,
                  ),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _RecordSummary extends StatelessWidget {
  const _RecordSummary({
    required this.logCount,
    required this.alertCount,
    required this.eventCount,
  });

  final int logCount;
  final int alertCount;
  final int eventCount;

  @override
  Widget build(BuildContext context) {
    final chips = [
      _RecordCountChip(
        icon: Icons.fact_check_outlined,
        label: 'Detection logs',
        count: logCount,
        color: AppColors.teal,
      ),
      _RecordCountChip(
        icon: Icons.notifications_outlined,
        label: 'Alerts',
        count: alertCount,
        color: AppColors.danger,
      ),
      _RecordCountChip(
        icon: Icons.video_library_outlined,
        label: 'Security & video events',
        count: eventCount,
        color: AppColors.warning,
      ),
    ];
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: LayoutBuilder(
        builder: (context, constraints) {
          if (constraints.maxWidth < AppBreakpoints.compact) {
            return Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                for (final chip in chips) ...[
                  chip,
                  if (chip != chips.last) const SizedBox(height: AppSpacing.sm),
                ],
              ],
            );
          }
          return Wrap(
            spacing: AppSpacing.sm,
            runSpacing: AppSpacing.sm,
            children: chips,
          );
        },
      ),
    );
  }
}

class _RecordCountChip extends StatelessWidget {
  const _RecordCountChip({
    required this.icon,
    required this.label,
    required this.count,
    required this.color,
  });

  final IconData icon;
  final String label;
  final int count;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      constraints: const BoxConstraints(maxWidth: 300),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: color.withAlpha(18),
        borderRadius: BorderRadius.circular(AppRadii.sm),
        border: Border.all(color: color.withAlpha(90)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 18, color: color),
          const SizedBox(width: AppSpacing.sm),
          Flexible(
            child: Text(
              '$label ($count)',
              overflow: TextOverflow.ellipsis,
              style: Theme.of(context).textTheme.labelLarge?.copyWith(
                color: AppColors.text,
                fontWeight: FontWeight.w800,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _SecurityFilterBar extends StatelessWidget {
  const _SecurityFilterBar({
    required this.selected,
    required this.visibleLogCount,
    required this.totalLogCount,
    required this.visibleAlertCount,
    required this.totalAlertCount,
    required this.visibleEventCount,
    required this.totalEventCount,
    required this.onToggle,
    required this.onClear,
  });

  final Set<SecurityRecordFilter> selected;
  final int visibleLogCount;
  final int totalLogCount;
  final int visibleAlertCount;
  final int totalAlertCount;
  final int visibleEventCount;
  final int totalEventCount;
  final ValueChanged<SecurityRecordFilter> onToggle;
  final VoidCallback onClear;

  @override
  Widget build(BuildContext context) {
    final unselectedForeground = Theme.of(context).colorScheme.onSurface;

    Widget buildFilterChip({
      required String label,
      required IconData icon,
      required Color accentColor,
      required bool selected,
      required ValueChanged<bool> onSelected,
      Key? key,
    }) {
      final foreground = selected ? Colors.white : unselectedForeground;
      return FilterChip(
        key: key,
        label: Text(
          label,
          style: TextStyle(color: foreground, fontWeight: FontWeight.w800),
        ),
        avatar: Icon(icon, size: 17, color: foreground),
        selected: selected,
        selectedColor: accentColor,
        checkmarkColor: Colors.white,
        showCheckmark: false,
        side: BorderSide(
          color: selected ? accentColor : AppColors.borderStrong,
          width: selected ? 2 : 1,
        ),
        onSelected: onSelected,
      );
    }

    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.surfaceSubtle,
        borderRadius: BorderRadius.circular(AppRadii.sm),
        border: Border.all(color: AppColors.border),
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 8, 8, 8),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            LayoutBuilder(
              builder: (context, constraints) {
                final title = Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      Icons.filter_alt_outlined,
                      size: 18,
                      color: AppColors.teal,
                    ),
                    const SizedBox(width: AppSpacing.sm),
                    Text(
                      'Security filters',
                      style: Theme.of(context).textTheme.labelLarge?.copyWith(
                        color: AppColors.text,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                  ],
                );
                final summary = Text(
                  '$visibleLogCount/$totalLogCount logs • '
                  '$visibleAlertCount/$totalAlertCount alerts • '
                  '$visibleEventCount/$totalEventCount events',
                  style: TextStyle(
                    color: AppColors.textMuted,
                    fontSize: 11,
                    fontWeight: FontWeight.w600,
                  ),
                );
                final clearButton = selected.isEmpty
                    ? null
                    : IconButton(
                        onPressed: onClear,
                        visualDensity: VisualDensity.compact,
                        tooltip: context.tr('Clear filters'),
                        icon: const Icon(
                          Icons.filter_alt_off_outlined,
                          size: 19,
                        ),
                      );

                if (constraints.maxWidth < AppBreakpoints.compact) {
                  return Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(children: [title, const Spacer(), ?clearButton]),
                      const SizedBox(height: AppSpacing.xs),
                      summary,
                    ],
                  );
                }

                return Row(
                  children: [title, const Spacer(), summary, ?clearButton],
                );
              },
            ),
            const SizedBox(height: AppSpacing.xs),
            SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Row(
                children: [
                  Padding(
                    padding: const EdgeInsets.only(right: AppSpacing.sm),
                    child: buildFilterChip(
                      label: 'All events',
                      icon: Icons.select_all,
                      accentColor: AppColors.teal,
                      selected: selected.isEmpty,
                      onSelected: (_) => onClear(),
                    ),
                  ),
                  ...SecurityRecordFilter.values.map(
                    (filter) => Padding(
                      padding: const EdgeInsets.only(right: AppSpacing.sm),
                      child: buildFilterChip(
                        key: ValueKey('security-filter-${filter.name}'),
                        label: filter.label,
                        icon: filter.icon,
                        accentColor: filter.accentColor,
                        selected: selected.contains(filter),
                        onSelected: (_) => onToggle(filter),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _UnknownPersonLabels {
  _UnknownPersonLabels({
    required List<DetectionLogModel> logs,
    required List<AlertModel> alerts,
  }) {
    final unknownLogs = logs.where((log) => log.status != 'known').toList()
      ..sort((a, b) {
        final timeComparison = a.detectedAt.compareTo(b.detectedAt);
        if (timeComparison != 0) return timeComparison;
        return a.id.compareTo(b.id);
      });

    final sessionNextIndexes = <int, int>{};
    for (final log in unknownLogs) {
      final trackId = log.trackId;
      if (trackId != null) {
        _labelsByLogId[log.id] = _format(trackId);
        continue;
      }

      final nextIndex = sessionNextIndexes[log.sessionId] ?? 1;
      _labelsByLogId[log.id] = _format(nextIndex);
      sessionNextIndexes[log.sessionId] = nextIndex + 1;
    }

    for (final alert in alerts.where(
      (alert) =>
          alert.alertType == 'restricted_area' && alert.detectionLogId != null,
    )) {
      _restrictedAlertsByLogId[alert.detectionLogId!] = alert;
    }

    final unlinkedUnknownAlerts =
        alerts
            .where(
              (alert) =>
                  _isUnknownAlert(alert) &&
                  (alert.detectionLogId == null ||
                      !_labelsByLogId.containsKey(alert.detectionLogId)),
            )
            .toList()
          ..sort((a, b) {
            final timeComparison = a.createdAt.compareTo(b.createdAt);
            if (timeComparison != 0) return timeComparison;
            return a.id.compareTo(b.id);
          });

    final nextIndex = _labelsByLogId.length + 1;
    for (final entry in unlinkedUnknownAlerts.indexed) {
      _labelsByAlertId[entry.$2.id] = _format(nextIndex + entry.$1);
    }
  }

  final Map<int, String> _labelsByLogId = {};
  final Map<int, String> _labelsByAlertId = {};
  final Map<int, AlertModel> _restrictedAlertsByLogId = {};

  String labelForLog(DetectionLogModel log) {
    if (log.status == 'known') {
      return '${log.memberName ?? 'Known person'} detected';
    }
    final unknownLabel = _labelsByLogId[log.id] ?? 'Unknown Person';
    final restrictedAlert = _restrictedAlertsByLogId[log.id];
    if (restrictedAlert != null) {
      final areaName = _restrictedAreaName(restrictedAlert.message);
      if (areaName != null) return '$unknownLabel lingering around $areaName';
    }
    return '$unknownLabel detected';
  }

  String labelForAlert(AlertModel alert) {
    if (alert.alertType == 'restricted_area') {
      final areaName = _restrictedAreaName(alert.message);
      final unknownLabel = _unknownLabelForAlert(alert);
      if (areaName != null) return '$unknownLabel lingering around $areaName';
      return '$unknownLabel lingering around a restricted area';
    }
    if (alert.alertType == 'unknown_person') {
      return '${_unknownLabelForAlert(alert)} detected';
    }
    if (!_messageMentionsUnknownPerson(alert)) {
      return _cleanAlertMessage(alert.message);
    }
    return '${_unknownLabelForAlert(alert)} detected';
  }

  String _unknownLabelForAlert(AlertModel alert) {
    final logId = alert.detectionLogId;
    if (logId != null && _labelsByLogId.containsKey(logId)) {
      return _labelsByLogId[logId]!;
    }
    return _labelsByAlertId[alert.id] ?? 'Unknown Person';
  }

  static bool _isUnknownAlert(AlertModel alert) =>
      alert.alertType == 'unknown_person' ||
      alert.alertType == 'restricted_area' ||
      _messageMentionsUnknownPerson(alert);

  static bool _messageMentionsUnknownPerson(AlertModel alert) =>
      alert.message.toLowerCase().contains('unknown person');

  static String _format(int index) =>
      'Unknown Person ${index.toString().padLeft(2, '0')}';

  static String _cleanAlertMessage(String message) {
    return message.replaceAll(
      RegExp(r'\s+on track\s+\d+', caseSensitive: false),
      '',
    );
  }

  static String? _restrictedAreaName(String message) {
    final cleanMessage = _cleanAlertMessage(message).trim();
    final enteredMatch = RegExp(
      r'unknown person entered\s+(.+)$',
      caseSensitive: false,
    ).firstMatch(cleanMessage);
    if (enteredMatch != null) return enteredMatch.group(1)?.trim();

    final inMatch = RegExp(
      r'unknown person(?:\s+\d+)?\s+in\s+(.+)$',
      caseSensitive: false,
    ).firstMatch(cleanMessage);
    return inMatch?.group(1)?.trim();
  }
}

enum _UnifiedRecordKind { detection, alert, securityEvent }

class _UnifiedSecurityRecord {
  const _UnifiedSecurityRecord._({
    required this.kind,
    required this.id,
    required this.occurredAt,
    this.log,
    this.alert,
    this.event,
  });

  factory _UnifiedSecurityRecord.fromLog(DetectionLogModel log) =>
      _UnifiedSecurityRecord._(
        kind: _UnifiedRecordKind.detection,
        id: log.id,
        occurredAt: _parseTimestamp(log.detectedAt),
        log: log,
      );

  factory _UnifiedSecurityRecord.fromAlert(AlertModel alert) =>
      _UnifiedSecurityRecord._(
        kind: _UnifiedRecordKind.alert,
        id: alert.id,
        occurredAt: _parseTimestamp(alert.createdAt),
        alert: alert,
      );

  factory _UnifiedSecurityRecord.fromEvent(SecurityEventModel event) =>
      _UnifiedSecurityRecord._(
        kind: _UnifiedRecordKind.securityEvent,
        id: event.id,
        occurredAt: _parseTimestamp(event.createdAt),
        event: event,
      );

  final _UnifiedRecordKind kind;
  final int id;
  final DateTime occurredAt;
  final DetectionLogModel? log;
  final AlertModel? alert;
  final SecurityEventModel? event;

  static DateTime _parseTimestamp(String value) =>
      DateTime.tryParse(value)?.toUtc() ??
      DateTime.fromMillisecondsSinceEpoch(0, isUtc: true);

  static List<_UnifiedSecurityRecord> merge({
    required List<DetectionLogModel> logs,
    required List<AlertModel> alerts,
    required List<SecurityEventModel> events,
  }) {
    final records = <_UnifiedSecurityRecord>[
      ...logs.map(_UnifiedSecurityRecord.fromLog),
      ...alerts.map(_UnifiedSecurityRecord.fromAlert),
      ...events.map(_UnifiedSecurityRecord.fromEvent),
    ];
    records.sort((a, b) {
      final byTime = b.occurredAt.compareTo(a.occurredAt);
      if (byTime != 0) return byTime;
      final byKind = a.kind.index.compareTo(b.kind.index);
      if (byKind != 0) return byKind;
      return b.id.compareTo(a.id);
    });
    return records;
  }
}

class _UnifiedRecordsFeed extends StatelessWidget {
  const _UnifiedRecordsFeed({
    required this.records,
    required this.filtered,
    required this.unknownLabels,
    required this.loading,
    required this.deletingLogs,
    required this.deletingAlerts,
    required this.selectedLogIds,
    required this.selectedAlertIds,
    required this.onToggleLogSelection,
    required this.onToggleAlertSelection,
    required this.onToggleAlertRead,
    required this.onDeleteAllLogs,
    required this.onDeleteAllAlerts,
    required this.totalLogCount,
    required this.totalAlertCount,
  });

  final List<_UnifiedSecurityRecord> records;
  final bool filtered;
  final _UnknownPersonLabels unknownLabels;
  final bool loading;
  final bool deletingLogs;
  final bool deletingAlerts;
  final Set<int> selectedLogIds;
  final Set<int> selectedAlertIds;
  final void Function(DetectionLogModel log, bool selected)
  onToggleLogSelection;
  final void Function(AlertModel alert, bool selected) onToggleAlertSelection;
  final ValueChanged<AlertModel> onToggleAlertRead;
  final VoidCallback onDeleteAllLogs;
  final VoidCallback onDeleteAllAlerts;
  final int totalLogCount;
  final int totalAlertCount;

  @override
  Widget build(BuildContext context) {
    if (loading && records.isEmpty) {
      return const _LoadingRows(label: 'Loading security activity');
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _TabActionRow(
          title: 'All security activity (${records.length})',
          action: Wrap(
            spacing: AppSpacing.sm,
            runSpacing: AppSpacing.sm,
            children: [
              OutlinedButton.icon(
                onPressed: totalLogCount == 0 || deletingLogs
                    ? null
                    : onDeleteAllLogs,
                icon: const Icon(Icons.delete_sweep_outlined),
                label: Text('Delete all logs'),
              ),
              OutlinedButton.icon(
                onPressed: totalAlertCount == 0 || deletingAlerts
                    ? null
                    : onDeleteAllAlerts,
                icon: const Icon(Icons.notifications_off_outlined),
                label: Text('Delete all alerts'),
              ),
            ],
          ),
        ),
        const SizedBox(height: AppSpacing.sm),
        Expanded(
          child: records.isEmpty
              ? EmptyPanel(
                  icon: Icons.inbox_outlined,
                  title: filtered
                      ? 'No matching security activity'
                      : 'No security activity yet',
                  message: filtered
                      ? 'Try selecting a different security filter.'
                      : 'Live detections, alerts, and uploaded-video events will appear here.',
                )
              : ListView.builder(
                  itemCount: records.length,
                  itemBuilder: (context, index) {
                    final record = records[index];
                    return KeyedSubtree(
                      key: ValueKey('unified-${record.kind.name}-${record.id}'),
                      child: switch (record.kind) {
                        _UnifiedRecordKind.detection => _buildDetection(
                          record.log!,
                        ),
                        _UnifiedRecordKind.alert => _buildAlert(record.alert!),
                        _UnifiedRecordKind.securityEvent => _SecurityEventRow(
                          event: record.event!,
                        ),
                      },
                    );
                  },
                ),
        ),
      ],
    );
  }

  Widget _buildDetection(DetectionLogModel log) => _DetectionLogRow(
    log: log,
    title: unknownLabels.labelForLog(log),
    selected: selectedLogIds.contains(log.id),
    deleting: deletingLogs,
    onSelected: (selected) => onToggleLogSelection(log, selected),
  );

  Widget _buildAlert(AlertModel alert) => _AlertRow(
    alert: alert,
    title: unknownLabels.labelForAlert(alert),
    selected: selectedAlertIds.contains(alert.id),
    deleting: deletingAlerts,
    onSelected: (selected) => onToggleAlertSelection(alert, selected),
    onToggleRead: () => onToggleAlertRead(alert),
  );
}

class _SecurityEventRow extends StatelessWidget {
  const _SecurityEventRow({required this.event});

  final SecurityEventModel event;

  bool get _danger => const {
    'fighting',
    'violence',
    'fire_smoke',
    'shooting',
    'weapon_drawn',
    'weapon_present',
    'knife_threat',
    'knife_present',
  }.contains(event.eventType);

  IconData get _icon => switch (event.eventType) {
    'fire_smoke' => Icons.local_fire_department,
    'fighting' || 'violence' => Icons.sports_mma,
    'shooting' || 'weapon_drawn' || 'weapon_present' => Icons.gps_fixed,
    'knife_threat' || 'knife_present' => Icons.warning_amber_rounded,
    'robbery_motorbike' => Icons.two_wheeler,
    'robbery_backpack' ||
    'robbery_phone' ||
    'theft' ||
    'possible_theft' => Icons.front_hand_outlined,
    _ => Icons.shield_outlined,
  };

  String get _title => event.eventType
      .split('_')
      .map(
        (word) => word.isEmpty
            ? word
            : '${word[0].toUpperCase()}${word.substring(1)}',
      )
      .join(' ');

  String _formatPosition(double seconds) {
    final minutes = seconds ~/ 60;
    final remainder = (seconds % 60).floor();
    return '${minutes.toString().padLeft(2, '0')}:${remainder.toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    final confidence = '${(event.confidence * 100).toStringAsFixed(1)}%';
    final range = event.startTimestamp == event.endTimestamp
        ? _formatPosition(event.startTimestamp)
        : '${_formatPosition(event.startTimestamp)}–${_formatPosition(event.endTimestamp)}';
    final object = event.detectedLabel == null
        ? ''
        : ' • ${event.detectedLabel}';
    return _SelectableRecordCard(
      selected: false,
      severe: _danger,
      recordType: event.sourceType == 'qa_video'
          ? 'UPLOADED VIDEO EVENT'
          : 'SECURITY EVENT',
      recordTypeColor: AppColors.warning,
      icon: Icon(_icon, color: _danger ? AppColors.danger : AppColors.warning),
      title: '$_title • Confidence $confidence',
      subtitle: '${event.sourceName}$object • $range',
      timestamp: formatBackendTimestamp(event.createdAt),
      onTap: null,
    );
  }
}

class _TabActionRow extends StatelessWidget {
  const _TabActionRow({required this.title, required this.action});

  final String title;
  final Widget action;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final text = Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              title,
              style: Theme.of(context).textTheme.titleSmall?.copyWith(
                fontWeight: FontWeight.w900,
                color: AppColors.text,
              ),
            ),
          ],
        );

        if (constraints.maxWidth < AppBreakpoints.compact) {
          return Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              text,
              const SizedBox(height: AppSpacing.md),
              action,
            ],
          );
        }

        return Row(
          children: [
            Expanded(child: text),
            const SizedBox(width: AppSpacing.md),
            action,
          ],
        );
      },
    );
  }
}

class _DetectionLogRow extends StatelessWidget {
  const _DetectionLogRow({
    required this.log,
    required this.title,
    required this.selected,
    required this.deleting,
    required this.onSelected,
  });

  final DetectionLogModel log;
  final String title;
  final bool selected;
  final bool deleting;
  final ValueChanged<bool> onSelected;

  bool get isKnown => log.status == 'known';

  @override
  Widget build(BuildContext context) {
    return _SelectableRecordCard(
      selected: selected,
      severe: !isKnown,
      recordType: 'DETECTION LOG',
      recordTypeColor: AppColors.teal,
      icon: Icon(
        isKnown ? Icons.verified_user : Icons.person_search,
        color: isKnown ? AppColors.success : AppColors.warning,
      ),
      title: title,
      subtitle: log.cameraName,
      timestamp: formatBackendTimestamp(log.detectedAt),
      onTap: deleting ? null : () => onSelected(!selected),
    );
  }
}

class _AlertRow extends StatelessWidget {
  const _AlertRow({
    required this.alert,
    required this.title,
    required this.selected,
    required this.deleting,
    required this.onSelected,
    required this.onToggleRead,
  });

  final AlertModel alert;
  final String title;
  final bool selected;
  final bool deleting;
  final ValueChanged<bool> onSelected;
  final VoidCallback onToggleRead;

  IconData get _categoryIcon {
    switch (alert.category) {
      case AlertCategory.knifeThreat:
      case AlertCategory.weaponDrawn:
        return Icons.warning_amber_rounded;
      case AlertCategory.fireSmoke:
        return Icons.local_fire_department;
      case AlertCategory.theft:
        return Icons.front_hand_outlined;
      case AlertCategory.loitering:
        return Icons.timelapse;
      case AlertCategory.restrictedArea:
        return Icons.fence;
      case AlertCategory.unknownPerson:
        return Icons.person_off_outlined;
      default:
        return alert.isRead
            ? Icons.notifications_none
            : Icons.notification_important;
    }
  }

  Color get _categoryColor {
    switch (alert.category) {
      case AlertCategory.knifeThreat:
      case AlertCategory.weaponDrawn:
      case AlertCategory.fireSmoke:
      case AlertCategory.violence:
        return AppColors.danger;
      case AlertCategory.theft:
      case AlertCategory.restrictedArea:
        return AppColors.warning;
      case AlertCategory.loitering:
        return Colors.deepPurple;
      default:
        return alert.isRead ? AppColors.textMuted : AppColors.danger;
    }
  }

  @override
  Widget build(BuildContext context) {
    return _SelectableRecordCard(
      selected: selected,
      severe: !alert.isRead,
      recordType: 'ALERT',
      recordTypeColor: AppColors.danger,
      icon: Stack(
        clipBehavior: Clip.none,
        children: [
          Icon(_categoryIcon, color: _categoryColor),
          if (!alert.isRead)
            Positioned(
              right: -1,
              top: -1,
              child: Container(
                width: 8,
                height: 8,
                decoration: BoxDecoration(
                  color: _categoryColor,
                  shape: BoxShape.circle,
                ),
              ),
            ),
        ],
      ),
      title: '${alert.categoryTitle}: $title',
      subtitle: '${alert.cameraName} • ${alert.message}',
      timestamp: formatBackendTimestamp(alert.createdAt),
      trailing: TextButton(
        onPressed: onToggleRead,
        child: Text(alert.isRead ? 'Mark unread' : 'Mark read'),
      ),
      onTap: deleting ? null : () => onSelected(!selected),
    );
  }
}

class _SelectableRecordCard extends StatelessWidget {
  const _SelectableRecordCard({
    required this.selected,
    required this.severe,
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.timestamp,
    required this.onTap,
    required this.recordType,
    required this.recordTypeColor,
    this.trailing,
  });

  final bool selected;
  final bool severe;
  final Widget icon;
  final String title;
  final String subtitle;
  final String timestamp;
  final VoidCallback? onTap;
  final String recordType;
  final Color recordTypeColor;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final borderColor = selected
        ? AppColors.teal
        : severe
        ? AppColors.dangerBorder
        : AppColors.border;
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: Card(
        color: severe ? AppColors.warning.withAlpha(10) : AppColors.surface,
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(AppRadii.sm),
          child: Container(
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(AppRadii.sm),
              border: Border.all(color: borderColor),
            ),
            padding: const EdgeInsets.all(AppSpacing.md),
            child: LayoutBuilder(
              builder: (context, constraints) {
                final content = Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    SizedBox(
                      width: 48,
                      height: 48,
                      child: Center(
                        child: selected
                            ? Icon(Icons.check_box, color: AppColors.teal)
                            : null,
                      ),
                    ),
                    const SizedBox(width: AppSpacing.sm),
                    SizedBox(width: 32, child: Center(child: icon)),
                    const SizedBox(width: AppSpacing.md),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 7,
                              vertical: 3,
                            ),
                            decoration: BoxDecoration(
                              color: recordTypeColor.withAlpha(20),
                              borderRadius: BorderRadius.circular(999),
                              border: Border.all(
                                color: recordTypeColor.withAlpha(90),
                              ),
                            ),
                            child: Text(
                              recordType,
                              style: Theme.of(context).textTheme.labelSmall
                                  ?.copyWith(
                                    color: recordTypeColor,
                                    fontWeight: FontWeight.w900,
                                  ),
                            ),
                          ),
                          const SizedBox(height: AppSpacing.xs),
                          Text(
                            title,
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                            style: Theme.of(context).textTheme.titleSmall
                                ?.copyWith(
                                  fontWeight: FontWeight.w900,
                                  color: AppColors.text,
                                ),
                          ),
                          const SizedBox(height: AppSpacing.xs),
                          Text(
                            '$subtitle · $timestamp',
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                            style: Theme.of(context).textTheme.bodySmall
                                ?.copyWith(color: AppColors.textMuted),
                          ),
                        ],
                      ),
                    ),
                  ],
                );

                if (trailing == null ||
                    constraints.maxWidth < AppBreakpoints.compact) {
                  return Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      content,
                      if (trailing != null) ...[
                        const SizedBox(height: AppSpacing.sm),
                        Align(
                          alignment: Alignment.centerRight,
                          child: trailing!,
                        ),
                      ],
                    ],
                  );
                }

                return Row(
                  children: [
                    Expanded(child: content),
                    const SizedBox(width: AppSpacing.md),
                    trailing!,
                  ],
                );
              },
            ),
          ),
        ),
      ),
    );
  }
}

class _SelectionToolbar extends StatelessWidget {
  const _SelectionToolbar({
    required this.label,
    required this.deleting,
    required this.onClear,
    required this.onDelete,
  });

  final String label;
  final bool deleting;
  final VoidCallback onClear;
  final VoidCallback onDelete;

  @override
  Widget build(BuildContext context) {
    return Card(
      color: AppColors.tealSoft,
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.md),
        child: Row(
          children: [
            Expanded(
              child: Text(
                label,
                style: Theme.of(context).textTheme.titleSmall?.copyWith(
                  color: AppColors.tealDark,
                  fontWeight: FontWeight.w900,
                ),
              ),
            ),
            TextButton(
              onPressed: deleting ? null : onClear,
              child: Text('Clear selection'),
            ),
            const SizedBox(width: AppSpacing.sm),
            FilledButton.icon(
              style: FilledButton.styleFrom(
                backgroundColor: AppColors.danger,
                foregroundColor: Colors.white,
              ),
              onPressed: deleting ? null : onDelete,
              icon: deleting
                  ? const SizedBox.square(
                      dimension: 16,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : Icon(Icons.delete_outline),
              label: Text(deleting ? 'Deleting' : 'Delete selected'),
            ),
          ],
        ),
      ),
    );
  }
}

class _LoadingRows extends StatelessWidget {
  const _LoadingRows({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              label,
              style: Theme.of(
                context,
              ).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w900),
            ),
            const SizedBox(height: AppSpacing.md),
            const LinearProgressIndicator(),
            const SizedBox(height: AppSpacing.lg),
            ...List.generate(
              4,
              (_) => Padding(
                padding: EdgeInsets.only(bottom: AppSpacing.md),
                child: LinearProgressIndicator(),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ErrorPanel extends StatelessWidget {
  const _ErrorPanel({required this.message, required this.onRetry});

  final String message;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    return EmptyPanel(
      icon: Icons.error_outline,
      title: 'Could not load logs',
      message: message,
      compact: true,
      action: OutlinedButton.icon(
        onPressed: onRetry,
        icon: Icon(Icons.refresh),
        label: Text('Retry'),
      ),
    );
  }
}
