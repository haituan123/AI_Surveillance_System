import 'package:flutter/material.dart' hide Text;

import '../core/app_settings.dart';
import '../theme/app_tokens.dart';
import 'localized_text.dart';

Future<void> showSettingsPanel(BuildContext context) {
  return showDialog<void>(
    context: context,
    builder: (context) => const _SettingsDialog(),
  );
}

class SettingsButton extends StatelessWidget {
  const SettingsButton({super.key, this.expanded = false});

  final bool expanded;

  @override
  Widget build(BuildContext context) {
    if (expanded) {
      return OutlinedButton.icon(
        onPressed: () => showSettingsPanel(context),
        icon: Icon(Icons.settings_outlined),
        label: Text('Settings'),
      );
    }
    return IconButton(
      onPressed: () => showSettingsPanel(context),
      tooltip: context.appSettings.isVietnamese ? 'Cài đặt' : 'Settings',
      icon: Icon(Icons.settings_outlined),
    );
  }
}

class _SettingsDialog extends StatelessWidget {
  const _SettingsDialog();

  @override
  Widget build(BuildContext context) {
    final settings = context.appSettings;
    return AlertDialog(
      title: const Row(
        children: [
          Icon(Icons.tune),
          SizedBox(width: AppSpacing.md),
          Text('Settings'),
        ],
      ),
      content: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 420),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              'Language',
              style: TextStyle(fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: AppSpacing.sm),
            SegmentedButton<AppLanguage>(
              segments: const [
                ButtonSegment(
                  value: AppLanguage.english,
                  icon: Icon(Icons.language),
                  label: Text('English'),
                ),
                ButtonSegment(
                  value: AppLanguage.vietnamese,
                  icon: Icon(Icons.translate),
                  label: Text('Vietnamese'),
                ),
              ],
              selected: {settings.language},
              onSelectionChanged: (selection) {
                settings.setLanguage(selection.first);
              },
            ),
            const SizedBox(height: AppSpacing.xl),
            Text(
              'Appearance',
              style: TextStyle(fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: AppSpacing.sm),
            SegmentedButton<ThemeMode>(
              segments: const [
                ButtonSegment(
                  value: ThemeMode.light,
                  icon: Icon(Icons.light_mode_outlined),
                  label: Text('Light'),
                ),
                ButtonSegment(
                  value: ThemeMode.dark,
                  icon: Icon(Icons.dark_mode_outlined),
                  label: Text('Dark'),
                ),
              ],
              selected: {settings.themeMode},
              onSelectionChanged: (selection) {
                settings.setThemeMode(selection.first);
              },
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: Text('Close'),
        ),
      ],
    );
  }
}
