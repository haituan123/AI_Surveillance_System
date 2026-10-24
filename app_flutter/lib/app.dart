import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';

import 'core/app_settings.dart';
import 'screens/main_shell.dart';
import 'theme/app_tokens.dart';

class FaceSecurityApp extends StatefulWidget {
  const FaceSecurityApp({super.key});

  @override
  State<FaceSecurityApp> createState() => _FaceSecurityAppState();
}

class _FaceSecurityAppState extends State<FaceSecurityApp> {
  late final AppSettingsController _settings;

  @override
  void initState() {
    super.initState();
    _settings = AppSettingsController();
    _settings.load();
  }

  @override
  void dispose() {
    _settings.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _settings,
      builder: (context, _) {
        AppColors.darkMode = _settings.isDark;
        return AppSettingsScope(
          controller: _settings,
          child: MaterialApp(
            title: 'AI Surveillance System',
            debugShowCheckedModeBanner: false,
            locale: _settings.locale,
            supportedLocales: const [Locale('en'), Locale('vi')],
            localizationsDelegates: const [
              GlobalMaterialLocalizations.delegate,
              GlobalWidgetsLocalizations.delegate,
              GlobalCupertinoLocalizations.delegate,
            ],
            theme: _buildTheme(Brightness.light),
            darkTheme: _buildTheme(Brightness.dark),
            themeMode: _settings.themeMode,
            home: const MainShell(),
          ),
        );
      },
    );
  }

  ThemeData _buildTheme(Brightness brightness) {
    final dark = brightness == Brightness.dark;
    final background = dark ? const Color(0xFF0F172A) : const Color(0xFFF6F8FA);
    final surface = dark ? const Color(0xFF172033) : Colors.white;
    final border = dark ? const Color(0xFF334155) : const Color(0xFFE5E7EB);
    final borderStrong =
        dark ? const Color(0xFF475569) : const Color(0xFFD1D5DB);
    final text = dark ? const Color(0xFFF8FAFC) : const Color(0xFF111827);
    return ThemeData(
      useMaterial3: true,
      colorScheme: ColorScheme.fromSeed(
        seedColor: AppColors.teal,
        brightness: brightness,
        surface: surface,
      ),
      scaffoldBackgroundColor: background,
      appBarTheme: AppBarTheme(
        backgroundColor: background,
        centerTitle: false,
        elevation: 0,
        titleTextStyle: TextStyle(
          color: text,
          fontSize: 20,
          fontWeight: FontWeight.w700,
        ),
      ),
      cardTheme: CardThemeData(
        color: surface,
        elevation: 0,
        margin: EdgeInsets.zero,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppRadii.sm),
          side: BorderSide(color: border),
        ),
      ),
      chipTheme: ChipThemeData(
        backgroundColor: surface,
        side: BorderSide(color: border),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppRadii.sm),
        ),
        labelStyle: TextStyle(fontWeight: FontWeight.w700),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: AppColors.teal,
          foregroundColor: Colors.white,
          minimumSize: const Size(44, 44),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(AppRadii.sm),
          ),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: AppColors.tealDark,
          minimumSize: const Size(44, 44),
          side: BorderSide(color: AppColors.borderStrong),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(AppRadii.sm),
          ),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: surface,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(AppRadii.sm),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(AppRadii.sm),
          borderSide: BorderSide(color: borderStrong),
        ),
      ),
    );
  }
}
