import 'package:flutter/material.dart' hide Text;

import '../theme/app_tokens.dart';
import 'localized_text.dart';

enum StatusBadgeTone { neutral, success, warning, danger }

class StatusBadge extends StatelessWidget {
  const StatusBadge({
    super.key,
    required this.label,
    this.icon,
    this.tone = StatusBadgeTone.neutral,
  });

  final String label;
  final IconData? icon;
  final StatusBadgeTone tone;

  @override
  Widget build(BuildContext context) {
    final color = switch (tone) {
      StatusBadgeTone.success => AppColors.success,
      StatusBadgeTone.warning => AppColors.warning,
      StatusBadgeTone.danger => AppColors.danger,
      StatusBadgeTone.neutral => AppColors.textMuted,
    };

    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.md,
        vertical: AppSpacing.sm,
      ),
      decoration: BoxDecoration(
        color: color.withAlpha(20),
        borderRadius: BorderRadius.circular(AppRadii.sm),
        border: Border.all(color: color.withAlpha(61)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (icon != null) ...[
            Icon(icon, size: 16, color: color),
            const SizedBox(width: AppSpacing.sm),
          ],
          Text(
            label,
            style: Theme.of(context).textTheme.labelLarge?.copyWith(
                  color: color,
                  fontWeight: FontWeight.w800,
                ),
          ),
        ],
      ),
    );
  }
}
