import 'package:flutter/material.dart';

import '../theme/app_tokens.dart';

class AppPage extends StatelessWidget {
  const AppPage({
    super.key,
    required this.children,
    this.maxWidth = AppLayout.pageMaxWidth,
    this.alignment,
  });

  final List<Widget> children;
  final double maxWidth;
  final AlignmentGeometry? alignment;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final horizontalPadding = constraints.maxWidth >= AppBreakpoints.desktop
            ? AppSpacing.xxl
            : AppSpacing.lg;

        return SingleChildScrollView(
          padding: EdgeInsets.fromLTRB(
            horizontalPadding,
            constraints.maxWidth >= AppBreakpoints.desktop
                ? AppSpacing.xxl
                : AppSpacing.lg,
            horizontalPadding,
            AppSpacing.xxl,
          ),
          child: Align(
            alignment: alignment ??
                (constraints.maxWidth >= AppBreakpoints.desktop
                    ? Alignment.topLeft
                    : Alignment.topCenter),
            child: ConstrainedBox(
              constraints: BoxConstraints(maxWidth: maxWidth),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: children,
              ),
            ),
          ),
        );
      },
    );
  }
}
