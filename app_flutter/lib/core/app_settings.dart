import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

enum AppLanguage { english, vietnamese }

class AppSettingsController extends ChangeNotifier {
  static const _languageKey = 'app_language';
  static const _themeKey = 'app_theme';

  AppLanguage _language = AppLanguage.english;
  ThemeMode _themeMode = ThemeMode.light;

  AppLanguage get language => _language;
  ThemeMode get themeMode => _themeMode;
  Locale get locale =>
      Locale(_language == AppLanguage.vietnamese ? 'vi' : 'en');
  bool get isVietnamese => _language == AppLanguage.vietnamese;
  bool get isDark => _themeMode == ThemeMode.dark;

  Future<void> load() async {
    final preferences = await SharedPreferences.getInstance();
    _language = preferences.getString(_languageKey) == 'vi'
        ? AppLanguage.vietnamese
        : AppLanguage.english;
    _themeMode = preferences.getString(_themeKey) == 'dark'
        ? ThemeMode.dark
        : ThemeMode.light;
    notifyListeners();
  }

  Future<void> setLanguage(AppLanguage value) async {
    if (_language == value) return;
    _language = value;
    notifyListeners();
    final preferences = await SharedPreferences.getInstance();
    await preferences.setString(
        _languageKey, value == AppLanguage.vietnamese ? 'vi' : 'en');
  }

  Future<void> setThemeMode(ThemeMode value) async {
    if (_themeMode == value) return;
    _themeMode = value;
    notifyListeners();
    final preferences = await SharedPreferences.getInstance();
    await preferences.setString(
        _themeKey, value == ThemeMode.dark ? 'dark' : 'light');
  }
}

class AppSettingsScope extends InheritedNotifier<AppSettingsController> {
  const AppSettingsScope({
    super.key,
    required AppSettingsController controller,
    required super.child,
  }) : super(notifier: controller);

  static AppSettingsController of(BuildContext context) {
    final scope =
        context.dependOnInheritedWidgetOfExactType<AppSettingsScope>();
    assert(scope != null, 'AppSettingsScope was not found in the widget tree.');
    return scope!.notifier!;
  }
}

extension AppSettingsContext on BuildContext {
  AppSettingsController get appSettings => AppSettingsScope.of(this);
}
