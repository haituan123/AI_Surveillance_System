import 'package:flutter/material.dart';

class AppColors {
  const AppColors._();

  static bool darkMode = false;

  static const teal = Color(0xFF2563EB);
  static const tealDark = Color(0xFF1E40AF);
  static Color get tealSoft =>
      darkMode ? const Color(0xFF172554) : const Color(0xFFEFF6FF);
  static Color get tealMuted =>
      darkMode ? const Color(0xFF1E3A8A) : const Color(0xFFBFDBFE);

  static Color get background =>
      darkMode ? const Color(0xFF0F172A) : const Color(0xFFF6F8FA);
  static Color get surface => darkMode ? const Color(0xFF172033) : Colors.white;
  static Color get surfaceSubtle =>
      darkMode ? const Color(0xFF1E293B) : const Color(0xFFF9FAFB);
  static Color get border =>
      darkMode ? const Color(0xFF334155) : const Color(0xFFE5E7EB);
  static Color get borderStrong =>
      darkMode ? const Color(0xFF475569) : const Color(0xFFD1D5DB);

  static Color get text =>
      darkMode ? const Color(0xFFF8FAFC) : const Color(0xFF111827);
  static Color get textMuted =>
      darkMode ? const Color(0xFFCBD5E1) : const Color(0xFF6B7280);
  static Color get textSubtle =>
      darkMode ? const Color(0xFF94A3B8) : const Color(0xFF9CA3AF);

  static const success = Color(0xFF16A34A);
  static const warning = Color(0xFFB45309);
  static const danger = Color(0xFFB91C1C);
  static Color get dangerBorder =>
      darkMode ? const Color(0xFF7F1D1D) : const Color(0xFFFCA5A5);
  static const cameraCanvas = Color(0xFF111827);
  static const cameraBorder = Color(0xFF374151);
}

class AppSpacing {
  const AppSpacing._();

  static const xs = 4.0;
  static const sm = 8.0;
  static const md = 12.0;
  static const lg = 16.0;
  static const xl = 24.0;
  static const xxl = 32.0;
}

class AppRadii {
  const AppRadii._();

  static const sm = 8.0;
  static const md = 12.0;
}

class AppBreakpoints {
  const AppBreakpoints._();

  static const compact = 720.0;
  static const desktop = 1100.0;
}

class AppLayout {
  const AppLayout._();

  static const pageMaxWidth = 1280.0;
  static const formMaxWidth = 1040.0;
  static const dataMaxWidth = 1440.0;
  static const sidebarWidth = 260.0;
}
