import 'dart:async';

import 'package:flutter/material.dart' hide Text;
import 'package:http/http.dart' as http;

import '../core/api_config.dart';
import '../theme/app_tokens.dart';
import 'localized_text.dart';

class ConnectionChip extends StatefulWidget {
  const ConnectionChip({super.key});

  @override
  State<ConnectionChip> createState() => _ConnectionChipState();
}

class _ConnectionChipState extends State<ConnectionChip> {
  Timer? _timer;
  bool? _isOnline;

  @override
  void initState() {
    super.initState();
    _checkConnection();
    _timer = Timer.periodic(
      const Duration(seconds: 5),
      (_) => _checkConnection(),
    );
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _checkConnection() async {
    try {
      final response = await http
          .get(Uri.parse('${ApiConfig.baseUrl}/health'))
          .timeout(const Duration(seconds: 2));
      if (!mounted) return;
      setState(() => _isOnline = response.statusCode == 200);
    } catch (_) {
      if (!mounted) return;
      setState(() => _isOnline = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final isOnline = _isOnline == true;
    final isChecking = _isOnline == null;
    final label = isChecking
        ? 'Backend checking'
        : (isOnline ? 'Backend online' : 'Backend offline');
    final color = isChecking
        ? AppColors.textSubtle
        : (isOnline ? AppColors.teal : AppColors.danger);

    return Chip(
      avatar: Icon(Icons.circle, size: 12, color: color),
      label: Text(label),
      visualDensity: VisualDensity.compact,
      side: BorderSide(color: AppColors.border),
      backgroundColor: AppColors.surface,
      labelStyle: TextStyle(fontWeight: FontWeight.w700, color: color),
    );
  }
}
