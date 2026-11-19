import 'package:flutter/material.dart' hide Text;

import '../core/app_localization.dart';
import '../theme/app_tokens.dart';
import '../widgets/connection_chip.dart';
import '../widgets/localized_text.dart';
import '../widgets/settings_panel.dart';
import 'dashboard_screen.dart';
import 'logs_screen.dart';
import 'people_screen.dart';
import 'surveillance_screen.dart';
import 'video_qa_screen.dart';

class MainShell extends StatefulWidget {
  const MainShell({super.key});

  @override
  State<MainShell> createState() => _MainShellState();
}

class _MainShellState extends State<MainShell> {
  int _selectedIndex = 0;
  int _membersRefreshToken = 0;
  int _peopleNavigationRequest = 0;
  PeopleSection _peopleInitialSection = PeopleSection.registeredPeople;
  int _monitorNavigationRequest = 0;
  SurveillanceInitialMode _monitorInitialMode =
      SurveillanceInitialMode.liveMonitoring;
  bool _sidebarExpanded = true;

  List<_NavPage> get _pages => [
        _NavPage(
          title: 'Overview',
          icon: Icons.dashboard_outlined,
          selectedIcon: Icons.dashboard,
          child: DashboardScreen(
            onStartSurveillance: () =>
                _openMonitor(SurveillanceInitialMode.liveMonitoring),
            onQuickVideoScan: () =>
                _openMonitor(SurveillanceInitialMode.quickVideoScan),
            onStartInvestigation: () => _selectPage(3),
            onRegisterPerson: () => _openPeople(PeopleSection.registerPerson),
            onViewLogs: () => _selectPage(4),
          ),
        ),
        _NavPage(
          title: 'People',
          icon: Icons.people_alt_outlined,
          selectedIcon: Icons.people_alt,
          child: PeopleScreen(
            refreshToken: _membersRefreshToken,
            onMembersChanged: _notifyMembersChanged,
            initialSection: _peopleInitialSection,
            navigationRequest: _peopleNavigationRequest,
          ),
        ),
        _NavPage(
          title: 'Monitor',
          icon: Icons.videocam_outlined,
          selectedIcon: Icons.videocam,
          child: SurveillanceScreen(
            initialMode: _monitorInitialMode,
            navigationRequest: _monitorNavigationRequest,
          ),
        ),
        const _NavPage(
          title: 'Investigations',
          icon: Icons.psychology_outlined,
          selectedIcon: Icons.psychology,
          child: VideoQAScreen(),
        ),
        const _NavPage(
          title: 'Activity',
          icon: Icons.receipt_long_outlined,
          selectedIcon: Icons.receipt_long,
          child: LogsScreen(),
        ),
      ];

  void _selectPage(int index) {
    setState(() {
      if (index == 1) {
        _peopleInitialSection = PeopleSection.registeredPeople;
        _peopleNavigationRequest++;
        _membersRefreshToken++;
      }
      _selectedIndex = index;
    });
  }

  void _notifyMembersChanged() {
    setState(() => _membersRefreshToken++);
  }

  void _openPeople(PeopleSection initialSection) {
    setState(() {
      _peopleInitialSection = initialSection;
      _peopleNavigationRequest++;
      _selectedIndex = 1;
    });
  }

  void _openMonitor(SurveillanceInitialMode initialMode) {
    setState(() {
      _monitorInitialMode = initialMode;
      _monitorNavigationRequest++;
      _selectedIndex = 2;
    });
  }

  @override
  Widget build(BuildContext context) {
    final page = _pages[_selectedIndex];
    final viewportWidth = MediaQuery.sizeOf(context).width;
    final useSidebar = viewportWidth >= AppBreakpoints.desktop;
    final compactNavigation = viewportWidth < AppBreakpoints.compact;
    final body = SafeArea(
      child: IndexedStack(
        index: _selectedIndex,
        children: _pages.map((page) => page.child).toList(),
      ),
    );

    return Scaffold(
      appBar: useSidebar
          ? null
          : AppBar(
              title: Text(page.title),
              actions: const [
                SettingsButton(),
                Padding(
                  padding: EdgeInsets.only(right: 16),
                  child: ConnectionChip(),
                ),
              ],
            ),
      body: useSidebar
          ? Row(
              children: [
                _DesktopSidebar(
                  pages: _pages,
                  selectedIndex: _selectedIndex,
                  onSelected: _selectPage,
                  expanded: _sidebarExpanded,
                  onToggle: () =>
                      setState(() => _sidebarExpanded = !_sidebarExpanded),
                ),
                VerticalDivider(width: 1, color: AppColors.border),
                Expanded(child: body),
              ],
            )
          : body,
      bottomNavigationBar: useSidebar
          ? null
          : Semantics(
              container: true,
              label: context.tr('Primary navigation'),
              child: NavigationBarTheme(
                data: NavigationBarThemeData(
                  labelTextStyle: WidgetStatePropertyAll(
                    Theme.of(context).textTheme.labelSmall?.copyWith(
                          fontSize: compactNavigation ? 11 : 12,
                          fontWeight: FontWeight.w700,
                        ),
                  ),
                ),
                child: NavigationBar(
                  key: const ValueKey('mobile-navigation'),
                  selectedIndex: _selectedIndex,
                  labelBehavior: compactNavigation
                      ? NavigationDestinationLabelBehavior.onlyShowSelected
                      : NavigationDestinationLabelBehavior.alwaysShow,
                  onDestinationSelected: _selectPage,
                  destinations: _pages
                      .map(
                        (page) => NavigationDestination(
                          tooltip: context.tr(page.title),
                          icon: Icon(page.icon),
                          selectedIcon: Icon(page.selectedIcon),
                          label: context.tr(page.title),
                        ),
                      )
                      .toList(),
                ),
              ),
            ),
    );
  }
}

class _DesktopSidebar extends StatelessWidget {
  const _DesktopSidebar({
    required this.pages,
    required this.selectedIndex,
    required this.onSelected,
    required this.expanded,
    required this.onToggle,
  });

  final List<_NavPage> pages;
  final int selectedIndex;
  final ValueChanged<int> onSelected;
  final bool expanded;
  final VoidCallback onToggle;

  @override
  Widget build(BuildContext context) {
    final width =
        expanded ? AppLayout.sidebarWidth : AppLayout.compactSidebarWidth;
    final horizontalPadding = expanded ? AppSpacing.lg : AppSpacing.md;

    return AnimatedSize(
      duration: const Duration(milliseconds: 220),
      curve: Curves.easeInOutCubic,
      alignment: Alignment.centerLeft,
      clipBehavior: Clip.hardEdge,
      child: SafeArea(
        child: Container(
          key: const ValueKey('desktop-sidebar'),
          width: width,
          color: AppColors.surface,
          child: Padding(
            padding: EdgeInsets.fromLTRB(
              horizontalPadding,
              AppSpacing.xl,
              horizontalPadding,
              AppSpacing.lg,
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                if (expanded)
                  Row(
                    children: [
                      Container(
                        width: 42,
                        height: 42,
                        decoration: BoxDecoration(
                          color: AppColors.tealSoft,
                          borderRadius: BorderRadius.circular(AppRadii.sm),
                        ),
                        child: Icon(Icons.security, color: AppColors.teal),
                      ),
                      const SizedBox(width: AppSpacing.sm),
                      Expanded(
                        child: Text(
                          'AI Face Security',
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style:
                              Theme.of(context).textTheme.titleSmall?.copyWith(
                                    fontWeight: FontWeight.w900,
                                    color: AppColors.text,
                                  ),
                        ),
                      ),
                      IconButton(
                        onPressed: onToggle,
                        tooltip: context.tr('Collapse navigation'),
                        icon: const Icon(Icons.keyboard_double_arrow_left),
                      ),
                    ],
                  )
                else
                  IconButton(
                    onPressed: onToggle,
                    tooltip: context.tr('Expand navigation'),
                    icon: const Icon(Icons.keyboard_double_arrow_right),
                    color: AppColors.tealDark,
                  ),
                const SizedBox(height: AppSpacing.xl),
                ...pages.indexed.map(
                  (entry) => Padding(
                    padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                    child: _SidebarDestination(
                      page: entry.$2,
                      selected: entry.$1 == selectedIndex,
                      onTap: () => onSelected(entry.$1),
                      expanded: expanded,
                    ),
                  ),
                ),
                const Spacer(),
                Align(child: ConnectionChip(compact: !expanded)),
                const SizedBox(height: AppSpacing.sm),
                SettingsButton(expanded: expanded),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _SidebarDestination extends StatelessWidget {
  const _SidebarDestination({
    required this.page,
    required this.selected,
    required this.onTap,
    required this.expanded,
  });

  final _NavPage page;
  final bool selected;
  final VoidCallback onTap;
  final bool expanded;

  @override
  Widget build(BuildContext context) {
    final color = selected ? AppColors.tealDark : AppColors.textMuted;
    final destination = Semantics(
      button: true,
      selected: selected,
      label: context.tr(page.title),
      excludeSemantics: true,
      child: Material(
        color: selected ? AppColors.tealSoft : Colors.transparent,
        borderRadius: BorderRadius.circular(AppRadii.sm),
        child: InkWell(
          borderRadius: BorderRadius.circular(AppRadii.sm),
          focusColor: AppColors.tealMuted,
          hoverColor: AppColors.tealSoft,
          onTap: onTap,
          child: ConstrainedBox(
            constraints: const BoxConstraints(minHeight: 48),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md),
              child: Row(
                mainAxisAlignment: expanded
                    ? MainAxisAlignment.start
                    : MainAxisAlignment.center,
                children: [
                  Icon(selected ? page.selectedIcon : page.icon, color: color),
                  if (expanded) ...[
                    const SizedBox(width: AppSpacing.md),
                    Expanded(
                      child: Text(
                        page.title,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: Theme.of(context).textTheme.labelLarge?.copyWith(
                              color: color,
                              fontWeight:
                                  selected ? FontWeight.w900 : FontWeight.w700,
                            ),
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ),
      ),
    );

    return Tooltip(message: context.tr(page.title), child: destination);
  }
}

class _NavPage {
  const _NavPage({
    required this.title,
    required this.icon,
    required this.selectedIcon,
    required this.child,
  });

  final String title;
  final IconData icon;
  final IconData selectedIcon;
  final Widget child;
}
