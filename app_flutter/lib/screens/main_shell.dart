import 'package:flutter/material.dart' hide Text;

import '../core/app_localization.dart';
import '../theme/app_tokens.dart';
import '../widgets/connection_chip.dart';
import '../widgets/localized_text.dart';
import '../widgets/settings_panel.dart';
import 'dashboard_screen.dart';
import 'logs_screen.dart';
import 'members_screen.dart';
import 'register_screen.dart';
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

  List<_NavPage> get _pages => [
        _NavPage(
          title: 'Dashboard',
          icon: Icons.dashboard_outlined,
          selectedIcon: Icons.dashboard,
          child: DashboardScreen(
            onStartSurveillance: () => _selectPage(3),
            onRegisterPerson: () => _selectPage(2),
            onViewLogs: () => _selectPage(5),
          ),
        ),
        _NavPage(
          title: 'Members',
          icon: Icons.people_alt_outlined,
          selectedIcon: Icons.people_alt,
          child: MembersScreen(
            refreshToken: _membersRefreshToken,
            onMembersChanged: _notifyMembersChanged,
          ),
        ),
        _NavPage(
          title: 'Register',
          icon: Icons.person_add_alt_1_outlined,
          selectedIcon: Icons.person_add_alt_1,
          child: RegisterScreen(
            refreshToken: _membersRefreshToken,
            onMembersChanged: _notifyMembersChanged,
          ),
        ),
        const _NavPage(
          title: 'Surveillance',
          icon: Icons.videocam_outlined,
          selectedIcon: Icons.videocam,
          child: SurveillanceScreen(),
        ),
        const _NavPage(
          title: 'Video QA',
          icon: Icons.psychology_outlined,
          selectedIcon: Icons.psychology,
          child: VideoQAScreen(),
        ),
        const _NavPage(
          title: 'Logs',
          icon: Icons.receipt_long_outlined,
          selectedIcon: Icons.receipt_long,
          child: LogsScreen(),
        ),
      ];

  void _selectPage(int index) {
    setState(() {
      _selectedIndex = index;
      final selectedTitle = _pages[index].title;
      if (selectedTitle == 'Members' || selectedTitle == 'Register') {
        _membersRefreshToken++;
      }
    });
  }

  void _notifyMembersChanged() {
    setState(() => _membersRefreshToken++);
  }

  @override
  Widget build(BuildContext context) {
    final page = _pages[_selectedIndex];
    final useSidebar =
        MediaQuery.sizeOf(context).width >= AppBreakpoints.desktop;
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
                ),
                VerticalDivider(width: 1, color: AppColors.border),
                Expanded(child: body),
              ],
            )
          : body,
      bottomNavigationBar: useSidebar
          ? null
          : NavigationBar(
              selectedIndex: _selectedIndex,
              onDestinationSelected: _selectPage,
              destinations: _pages
                  .map(
                    (page) => NavigationDestination(
                      icon: Icon(page.icon),
                      selectedIcon: Icon(page.selectedIcon),
                      label: context.tr(page.title),
                    ),
                  )
                  .toList(),
            ),
    );
  }
}

class _DesktopSidebar extends StatelessWidget {
  const _DesktopSidebar({
    required this.pages,
    required this.selectedIndex,
    required this.onSelected,
  });

  final List<_NavPage> pages;
  final int selectedIndex;
  final ValueChanged<int> onSelected;

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Container(
        width: AppLayout.sidebarWidth,
        color: AppColors.surface,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(
            AppSpacing.lg,
            AppSpacing.xl,
            AppSpacing.lg,
            AppSpacing.lg,
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
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
                  const SizedBox(width: AppSpacing.md),
                  Expanded(
                    child: Text(
                      'AI Face Security',
                      style: Theme.of(context).textTheme.titleMedium?.copyWith(
                            fontWeight: FontWeight.w900,
                            color: AppColors.text,
                          ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: AppSpacing.xl),
              ...pages.indexed.map(
                (entry) => Padding(
                  padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                  child: _SidebarDestination(
                    page: entry.$2,
                    selected: entry.$1 == selectedIndex,
                    onTap: () => onSelected(entry.$1),
                  ),
                ),
              ),
              const Spacer(),
              const ConnectionChip(),
              const SizedBox(height: AppSpacing.sm),
              const SettingsButton(expanded: true),
            ],
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
  });

  final _NavPage page;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final color = selected ? AppColors.tealDark : AppColors.textMuted;
    return Material(
      color: selected ? AppColors.tealSoft : Colors.transparent,
      borderRadius: BorderRadius.circular(AppRadii.sm),
      child: InkWell(
        borderRadius: BorderRadius.circular(AppRadii.sm),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.md,
            vertical: AppSpacing.md,
          ),
          child: Row(
            children: [
              Icon(selected ? page.selectedIcon : page.icon, color: color),
              const SizedBox(width: AppSpacing.md),
              Expanded(
                child: Text(
                  page.title,
                  style: Theme.of(context).textTheme.labelLarge?.copyWith(
                        color: color,
                        fontWeight:
                            selected ? FontWeight.w900 : FontWeight.w700,
                      ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
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
