import 'package:flutter/material.dart' hide Text;

import '../theme/app_tokens.dart';
import 'localized_text.dart';

enum AppMessageTone { info, success, warning, danger }

class AppMessagePanel extends StatelessWidget {
  const AppMessagePanel({
    super.key,
    required this.title,
    required this.message,
    this.tone = AppMessageTone.info,
    this.action,
    this.compact = false,
  });

  final String title;
  final String message;
  final AppMessageTone tone;
  final Widget? action;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final color = _colorFor(tone);
    return DecoratedBox(
      decoration: BoxDecoration(
        color: color.withAlpha(16),
        border: Border.all(color: color.withAlpha(72)),
        borderRadius: BorderRadius.circular(AppRadii.sm),
      ),
      child: Padding(
        padding: EdgeInsets.all(compact ? AppSpacing.md : AppSpacing.lg),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(_iconFor(tone), color: color),
            const SizedBox(width: AppSpacing.md),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: Theme.of(context).textTheme.titleSmall?.copyWith(
                          color: color,
                          fontWeight: FontWeight.w900,
                        ),
                  ),
                  const SizedBox(height: AppSpacing.xs),
                  Text(
                    message,
                    style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                          color: AppColors.textMuted,
                          height: 1.35,
                        ),
                  ),
                  if (action != null) ...[
                    const SizedBox(height: AppSpacing.md),
                    action!,
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

void showAppSnackBar(
  BuildContext context, {
  required String message,
  AppMessageTone tone = AppMessageTone.info,
}) {
  final color = _colorFor(tone);
  ScaffoldMessenger.of(context).showSnackBar(
    SnackBar(
      content: Text(message),
      backgroundColor: tone == AppMessageTone.info ? null : color,
    ),
  );
}

String friendlyErrorMessage(Object error) {
  final message = error.toString().replaceFirst('Exception: ', '');
  final lower = message.toLowerCase();
  if (lower.contains('permission') || lower.contains('denied')) {
    return 'Permission denied. Allow camera/file access and try again.';
  }
  if (lower.contains('connection') ||
      lower.contains('socket') ||
      lower.contains('failed host lookup') ||
      lower.contains('connection refused')) {
    return 'Backend unavailable. Check that the backend server is running.';
  }
  if (message.startsWith('ApiException: ')) {
    return message.replaceFirst('ApiException: ', '');
  }
  return message;
}

AppMessageTone toneForError(Object error) {
  final lower = error.toString().toLowerCase();
  if (lower.contains('permission') || lower.contains('denied')) {
    return AppMessageTone.warning;
  }
  return AppMessageTone.danger;
}

Color _colorFor(AppMessageTone tone) {
  return switch (tone) {
    AppMessageTone.info => AppColors.teal,
    AppMessageTone.success => AppColors.success,
    AppMessageTone.warning => AppColors.warning,
    AppMessageTone.danger => AppColors.danger,
  };
}

IconData _iconFor(AppMessageTone tone) {
  return switch (tone) {
    AppMessageTone.info => Icons.info_outline,
    AppMessageTone.success => Icons.check_circle_outline,
    AppMessageTone.warning => Icons.warning_amber_outlined,
    AppMessageTone.danger => Icons.error_outline,
  };
}
