import 'dart:async';

import 'package:flutter/material.dart';

import '../core/timestamp_formatter.dart';
import '../models/security_models.dart';
import '../services/member_service.dart';
import '../services/security_service.dart';
import '../theme/app_tokens.dart';
import '../widgets/app_message.dart';
import '../widgets/app_page.dart';
import '../widgets/empty_panel.dart';
import '../widgets/header_block.dart';
import '../widgets/section_header.dart';
import '../widgets/status_tile.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({
    super.key,
    this.securityService,
    this.memberService = const MemberService(),
    this.onStartSurveillance,
    this.onRegisterPerson,
    this.onViewLogs,
  });

  final SecurityService? securityService;
  final MemberService memberService;
  final VoidCallback? onStartSurveillance;
  final VoidCallback? onRegisterPerson;
  final VoidCallback? onViewLogs;

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  late final SecurityService _security =
      widget.securityService ?? SecurityService();
  Timer? _timer;
  bool _online = false;
  bool _refreshInFlight = false;
  int _refreshFailures = 0;
  int? _memberCount;
  int? _unreadAlerts;
  SurveillanceStatusModel? _status;
  DetectionLogModel? _latest;
  List<AlertModel> _recentAlerts = const [];

  @override
  void initState() {
    super.initState();
    _refresh();
    _timer = Timer.periodic(const Duration(seconds: 5), (_) => _refresh());
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _refresh() async {
    if (_refreshInFlight) return;
    _refreshInFlight = true;
    try {
      final values = await Future.wait([
        _security.health(),
        widget.memberService.listMembers(),
        _security.surveillanceStatus(),
        _security.listAlerts(limit: 100),
        _security.listLogs(limit: 1),
      ]);
      if (!mounted) return;
      final alerts = values[3] as List<AlertModel>;
      final logs = values[4] as List<DetectionLogModel>;
      setState(() {
        _online = true;
        _refreshFailures = 0;
        _memberCount = (values[1] as List).length;
        _status = values[2] as SurveillanceStatusModel;
        _unreadAlerts = alerts.where((alert) => !alert.isRead).length;
        _recentAlerts = alerts.take(5).toList();
        _latest = logs.isEmpty ? null : logs.first;
      });
    } catch (_) {
      if (mounted) {
        _refreshFailures += 1;
        if (_refreshFailures < 3) return;
        setState(() {
          _online = false;
          _status = null;
        });
      }
    } finally {
      _refreshInFlight = false;
    }
  }

  @override
  Widget build(BuildContext context) {
    final running = _status?.running == true;

    return AppPage(
      maxWidth: AppLayout.dataMaxWidth,
      children: [
        HeaderBlock(
          title: 'Operational Overview',
          subtitle:
              'Monitor backend health, camera activity, recognition coverage, and recent alert activity.',
          icon: Icons.security,
        ),
        const SizedBox(height: AppSpacing.lg),
        if (!_online) ...[
          AppMessagePanel(
            title: 'Backend offline',
            message:
                'Live status, members, alerts, and logs could not be refreshed. Check the backend server and connection.',
            tone: AppMessageTone.danger,
            action: OutlinedButton.icon(
              onPressed: _refresh,
              icon: const Icon(Icons.refresh),
              label: const Text('Retry'),
            ),
          ),
          const SizedBox(height: AppSpacing.lg),
        ],
        LayoutBuilder(
          builder: (context, constraints) {
            final isWide = constraints.maxWidth >= AppBreakpoints.compact;
            final cards = [
              StatusTile(
                label: 'System status',
                value: _online ? 'Backend online' : 'Backend offline',
                icon: _online
                    ? Icons.cloud_done_outlined
                    : Icons.cloud_off_outlined,
              ),
              StatusTile(
                label: 'Camera status',
                value: running
                    ? '${_status!.fps.toStringAsFixed(1)} FPS'
                    : 'Stopped',
                icon: running ? Icons.videocam : Icons.videocam_off_outlined,
              ),
              StatusTile(
                label: 'Registered people',
                value: _memberCount?.toString() ?? '-',
                icon: Icons.groups_outlined,
              ),
              StatusTile(
                label: 'Unread alerts',
                value: _unreadAlerts?.toString() ?? '-',
                icon: Icons.warning_amber_outlined,
              ),
            ];
            return GridView.builder(
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                crossAxisCount: isWide ? 4 : 2,
                crossAxisSpacing: AppSpacing.md,
                mainAxisSpacing: AppSpacing.md,
                mainAxisExtent: isWide ? 124 : 136,
              ),
              itemCount: cards.length,
              itemBuilder: (context, index) => cards[index],
            );
          },
        ),
        const SizedBox(height: AppSpacing.xl),
        LayoutBuilder(
          builder: (context, constraints) {
            final isDesktop = constraints.maxWidth >= AppBreakpoints.desktop;
            final alerts = _RecentAlertsPanel(
              alerts: _recentAlerts,
              onViewLogs: widget.onViewLogs,
            );
            final latest = _LatestDetectionPanel(latest: _latest);

            if (!isDesktop) {
              return Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  alerts,
                  const SizedBox(height: AppSpacing.lg),
                  latest,
                ],
              );
            }

            return Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(flex: 3, child: alerts),
                const SizedBox(width: AppSpacing.lg),
                Expanded(flex: 2, child: latest),
              ],
            );
          },
        ),
      ],
    );
  }
}

class _RecentAlertsPanel extends StatelessWidget {
  const _RecentAlertsPanel({required this.alerts, required this.onViewLogs});

  final List<AlertModel> alerts;
  final VoidCallback? onViewLogs;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        SectionHeader(
          title: 'Recent alerts',
          trailing: TextButton.icon(
            onPressed: onViewLogs,
            icon: const Icon(Icons.open_in_new),
            label: const Text('View logs'),
          ),
        ),
        if (alerts.isEmpty)
          EmptyPanel(
            icon: Icons.notifications_none,
            title: 'No recent alerts',
            message: 'Unknown-person alerts from live mode will appear here.',
            compact: true,
            action: OutlinedButton.icon(
              onPressed: onViewLogs,
              icon: const Icon(Icons.receipt_long_outlined),
              label: const Text('Open logs'),
            ),
          )
        else
          ...alerts.map(
            (alert) {
              IconData icon = Icons.notifications_none;
              Color color = AppColors.danger;
              switch (alert.category) {
                case AlertCategory.knifeThreat:
                case AlertCategory.weaponDrawn:
                  icon = Icons.warning_amber_rounded;
                  color = AppColors.danger;
                  break;
                case AlertCategory.fireSmoke:
                  icon = Icons.local_fire_department;
                  color = Colors.deepOrange;
                  break;
                case AlertCategory.theft:
                  icon = Icons.front_hand_outlined;
                  color = AppColors.warning;
                  break;
                case AlertCategory.loitering:
                  icon = Icons.timelapse;
                  color = Colors.deepPurple;
                  break;
                case AlertCategory.restrictedArea:
                  icon = Icons.fence;
                  color = AppColors.warning;
                  break;
                case AlertCategory.unknownPerson:
                  icon = Icons.person_off_outlined;
                  color = AppColors.danger;
                  break;
                default:
                  icon = alert.isRead ? Icons.notifications_none : Icons.notification_important;
                  color = alert.isRead ? AppColors.textMuted : AppColors.danger;
              }

              return Padding(
                padding: const EdgeInsets.only(bottom: AppSpacing.md),
                child: Card(
                  child: ListTile(
                    leading: Icon(icon, color: alert.isRead ? AppColors.textMuted : color),
                    title: Text('${alert.categoryTitle}: ${alert.message}'),
                    subtitle: Text(
                      '${alert.cameraName} · ${formatBackendTimestamp(alert.createdAt)}',
                    ),
                  ),
                ),
              );
            },
          ),
      ],
    );
  }
}

class _LatestDetectionPanel extends StatelessWidget {
  const _LatestDetectionPanel({required this.latest});

  final DetectionLogModel? latest;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const SectionHeader(title: 'Latest detection'),
        if (latest == null)
          const EmptyPanel(
            icon: Icons.fact_check_outlined,
            title: 'No persistent live detection yet',
            message:
                'Uploaded-video results are temporary and do not appear here.',
            compact: true,
          )
        else
          Card(
            child: ListTile(
              leading: Icon(
                latest!.status == 'known'
                    ? Icons.verified_user
                    : Icons.warning_amber,
              ),
              title: Text(
                latest!.status == 'known'
                    ? '${latest!.memberName ?? 'Known person'} detected'
                    : 'Unknown Person 01 detected',
              ),
              subtitle: Text(
                '${latest!.cameraName} · ${formatBackendTimestamp(latest!.detectedAt)}',
              ),
            ),
          ),
      ],
    );
  }
}
