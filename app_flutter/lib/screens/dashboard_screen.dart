import 'dart:async';

import 'package:flutter/material.dart' hide Text;

import '../core/timestamp_formatter.dart';
import '../models/security_models.dart';
import '../services/member_service.dart';
import '../services/security_service.dart';
import '../theme/app_tokens.dart';
import '../widgets/app_message.dart';
import '../widgets/app_page.dart';
import '../widgets/empty_panel.dart';
import '../widgets/header_block.dart';
import '../widgets/localized_text.dart';
import '../widgets/section_header.dart';
import '../widgets/status_tile.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({
    super.key,
    this.securityService,
    this.memberService = const MemberService(),
    this.onStartSurveillance,
    this.onQuickVideoScan,
    this.onStartInvestigation,
    this.onRegisterPerson,
    this.onViewLogs,
  });

  final SecurityService? securityService;
  final MemberService memberService;
  final VoidCallback? onStartSurveillance;
  final VoidCallback? onQuickVideoScan;
  final VoidCallback? onStartInvestigation;
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
    final showFirstUseGuide = _memberCount == 0 && _latest == null;

    return AppPage(
      maxWidth: AppLayout.dataMaxWidth,
      children: [
        HeaderBlock(
          title: 'Overview',
          subtitle:
              'Review system health, live monitoring, recognition coverage, and recent security activity.',
          icon: Icons.security,
        ),
        const SizedBox(height: AppSpacing.lg),
        if (!_online) ...[
          AppMessagePanel(
            title: 'Backend offline',
            message:
                'Live status, members, alerts, and activity could not be refreshed. Check the backend server and connection.',
            tone: AppMessageTone.danger,
            action: OutlinedButton.icon(
              onPressed: _refresh,
              icon: Icon(Icons.refresh),
              label: Text('Retry'),
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
        _QuickActionsPanel(
          showFirstUseGuide: showFirstUseGuide,
          onRegisterPerson: widget.onRegisterPerson,
          onStartLiveMonitoring: widget.onStartSurveillance,
          onQuickVideoScan: widget.onQuickVideoScan,
          onStartInvestigation: widget.onStartInvestigation,
          onViewActivity: widget.onViewLogs,
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

class _QuickActionsPanel extends StatelessWidget {
  const _QuickActionsPanel({
    required this.showFirstUseGuide,
    required this.onRegisterPerson,
    required this.onStartLiveMonitoring,
    required this.onQuickVideoScan,
    required this.onStartInvestigation,
    required this.onViewActivity,
  });

  final bool showFirstUseGuide;
  final VoidCallback? onRegisterPerson;
  final VoidCallback? onStartLiveMonitoring;
  final VoidCallback? onQuickVideoScan;
  final VoidCallback? onStartInvestigation;
  final VoidCallback? onViewActivity;

  @override
  Widget build(BuildContext context) {
    final actions = [
      (
        key: const ValueKey('overview-register-action'),
        label: 'Register a person',
        icon: Icons.person_add_alt_1_outlined,
        onPressed: onRegisterPerson,
      ),
      (
        key: const ValueKey('overview-live-monitoring-action'),
        label: 'Start live monitoring',
        icon: Icons.videocam_outlined,
        onPressed: onStartLiveMonitoring,
      ),
      (
        key: const ValueKey('overview-quick-scan-action'),
        label: 'Run a quick video scan',
        icon: Icons.video_file_outlined,
        onPressed: onQuickVideoScan,
      ),
      (
        key: const ValueKey('overview-investigation-action'),
        label: 'Start a video investigation',
        icon: Icons.psychology_outlined,
        onPressed: onStartInvestigation,
      ),
      (
        key: const ValueKey('overview-activity-action'),
        label: 'View activity',
        icon: Icons.receipt_long_outlined,
        onPressed: onViewActivity,
      ),
    ];

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const SectionHeader(title: 'Quick actions'),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(AppSpacing.md),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Wrap(
                  spacing: AppSpacing.sm,
                  runSpacing: AppSpacing.sm,
                  children: actions
                      .map(
                        (action) => OutlinedButton.icon(
                          key: action.key,
                          onPressed: action.onPressed,
                          icon: Icon(action.icon),
                          label: Text(action.label),
                        ),
                      )
                      .toList(),
                ),
                if (showFirstUseGuide) ...[
                  const SizedBox(height: AppSpacing.md),
                  Divider(height: 1, color: AppColors.border),
                  const SizedBox(height: AppSpacing.md),
                  Text(
                    'Get started in three steps',
                    style: Theme.of(context).textTheme.titleSmall?.copyWith(
                          color: AppColors.text,
                          fontWeight: FontWeight.w900,
                        ),
                  ),
                  const SizedBox(height: AppSpacing.sm),
                  LayoutBuilder(
                    builder: (context, constraints) {
                      const steps = [
                        'Register people.',
                        'Start live monitoring or scan a video.',
                        'Review Activity or investigate footage.',
                      ];
                      if (constraints.maxWidth < AppBreakpoints.compact) {
                        return Column(
                          children: steps.indexed
                              .map(
                                (entry) => Padding(
                                  padding: const EdgeInsets.only(
                                    bottom: AppSpacing.sm,
                                  ),
                                  child: _FirstUseStep(
                                    number: entry.$1 + 1,
                                    label: entry.$2,
                                  ),
                                ),
                              )
                              .toList(),
                        );
                      }
                      return Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: steps.indexed
                            .map(
                              (entry) => Expanded(
                                child: Padding(
                                  padding: EdgeInsets.only(
                                    right: entry.$1 == steps.length - 1
                                        ? 0
                                        : AppSpacing.md,
                                  ),
                                  child: _FirstUseStep(
                                    number: entry.$1 + 1,
                                    label: entry.$2,
                                  ),
                                ),
                              ),
                            )
                            .toList(),
                      );
                    },
                  ),
                ],
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _FirstUseStep extends StatelessWidget {
  const _FirstUseStep({required this.number, required this.label});

  final int number;
  final String label;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        CircleAvatar(
          radius: 12,
          backgroundColor: AppColors.tealSoft,
          foregroundColor: AppColors.tealDark,
          child: Text(
            '$number',
            style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w900),
          ),
        ),
        const SizedBox(width: AppSpacing.sm),
        Expanded(
          child: Text(
            label,
            style: Theme.of(
              context,
            ).textTheme.bodyMedium?.copyWith(color: AppColors.textMuted),
          ),
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
            icon: Icon(Icons.open_in_new),
            label: Text('View activity'),
          ),
        ),
        if (alerts.isEmpty)
          EmptyPanel(
            icon: Icons.notifications_none,
            title: 'No recent alerts',
            message:
                'Saved unknown-person alerts from Live monitoring will appear here.',
            compact: true,
            action: OutlinedButton.icon(
              onPressed: onViewLogs,
              icon: Icon(Icons.receipt_long_outlined),
              label: Text('Open activity'),
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
                  icon = alert.isRead
                      ? Icons.notifications_none
                      : Icons.notification_important;
                  color = alert.isRead ? AppColors.textMuted : AppColors.danger;
              }

              return Padding(
                padding: const EdgeInsets.only(bottom: AppSpacing.md),
                child: Card(
                  child: ListTile(
                    leading: Icon(icon,
                        color: alert.isRead ? AppColors.textMuted : color),
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
                'Quick video scan results are temporary and do not appear in Overview or Activity.',
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
