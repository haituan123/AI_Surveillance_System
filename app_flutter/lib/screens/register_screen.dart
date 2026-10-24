import 'package:flutter/material.dart' hide Text;

import '../core/app_localization.dart';
import 'package:file_picker/file_picker.dart';

import '../models/member_model.dart';
import '../services/member_service.dart';
import '../theme/app_tokens.dart';
import '../widgets/app_message.dart';
import '../widgets/app_page.dart';
import '../widgets/header_block.dart';
import '../widgets/localized_text.dart';
import '../widgets/status_badge.dart';

class RegisterScreen extends StatefulWidget {
  const RegisterScreen({
    super.key,
    required this.refreshToken,
    required this.onMembersChanged,
  });

  final int refreshToken;
  final VoidCallback onMembersChanged;

  @override
  State<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends State<RegisterScreen> {
  final TextEditingController _nameController = TextEditingController();
  final MemberService _memberService = const MemberService();

  List<PlatformFile> _selectedImages = [];
  RegisterMemberResult? _lastResult;
  bool _isSubmitting = false;
  bool _hasSubmitted = false;
  String? _formError;

  bool get _hasName => _nameController.text.trim().isNotEmpty;
  bool get _hasImages => _selectedImages.isNotEmpty;
  bool get _canSubmit => !_isSubmitting && _hasName && _hasImages;

  @override
  void initState() {
    super.initState();
    _nameController.addListener(_onFormChanged);
  }

  @override
  void dispose() {
    _nameController
      ..removeListener(_onFormChanged)
      ..dispose();
    super.dispose();
  }

  void _onFormChanged() {
    setState(() => _formError = _hasSubmitted ? _validationMessage() : null);
  }

  Future<void> _pickImages() async {
    final FilePickerResult? result;
    try {
      result = await FilePicker.platform.pickFiles(
        allowMultiple: true,
        type: FileType.custom,
        allowedExtensions: ['jpg', 'jpeg', 'png', 'webp'],
        withData: true,
      );
    } catch (error) {
      if (!mounted) return;
      final message = friendlyErrorMessage(error);
      setState(() => _formError = message);
      _showMessage(message, isError: true);
      return;
    }

    if (result == null) {
      return;
    }

    final files = result.files;
    setState(() {
      _selectedImages = files;
      _formError = _hasSubmitted ? _validationMessage() : null;
    });
  }

  void _removeSelectedImage(int index) {
    setState(() {
      _selectedImages = [..._selectedImages]..removeAt(index);
      _formError = _hasSubmitted ? _validationMessage() : null;
    });
  }

  void _clearSelectedImages() {
    setState(() {
      _selectedImages = [];
      _formError = _hasSubmitted ? _validationMessage() : null;
    });
  }

  Future<void> _registerMember() async {
    final name = _nameController.text.trim();
    final validationMessage = _validationMessage();
    if (validationMessage != null) {
      setState(() {
        _hasSubmitted = true;
        _formError = validationMessage;
      });
      _showMessage(validationMessage, isError: true);
      return;
    }

    setState(() {
      _hasSubmitted = true;
      _isSubmitting = true;
      _formError = null;
    });
    try {
      final result = await _memberService.registerMember(
        name: name,
        images: _selectedImages,
      );
      if (!mounted) return;
      _nameController.clear();
      setState(() {
        _selectedImages = [];
        _lastResult = result;
        _formError = null;
        _hasSubmitted = false;
      });
      widget.onMembersChanged();
      _showMessage(result.message);
    } catch (error) {
      if (!mounted) return;
      final message = friendlyErrorMessage(error);
      setState(() {
        _lastResult = null;
        _formError = message;
      });
      _showMessage(message, isError: true);
    } finally {
      if (mounted) {
        setState(() => _isSubmitting = false);
      }
    }
  }

  String? _validationMessage() {
    if (!_hasName && !_hasImages) {
      return 'Enter a person name and choose at least one face image.';
    }
    if (!_hasName) return 'Enter a person name first.';
    if (!_hasImages) return 'Choose at least one face image.';
    return null;
  }

  void _showMessage(String message, {bool isError = false}) {
    showAppSnackBar(
      context,
      message: message,
      tone: isError ? AppMessageTone.danger : AppMessageTone.success,
    );
  }

  @override
  Widget build(BuildContext context) {
    final formCard = Card(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              'Person details',
              style: Theme.of(context).textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.w900,
                    color: AppColors.text,
                  ),
            ),
            const SizedBox(height: AppSpacing.md),
            TextField(
              controller: _nameController,
              enabled: !_isSubmitting,
              decoration: InputDecoration(
                labelText: context.tr('Person name'),
                hintText: context.tr('Enter the name used in alerts and logs'),
                prefixIcon: Icon(Icons.badge_outlined),
              ),
              textInputAction: TextInputAction.next,
            ),
            const SizedBox(height: AppSpacing.lg),
            _ImagePickerPanel(
              images: _selectedImages,
              submitting: _isSubmitting,
              onPick: _pickImages,
              onRemove: _isSubmitting ? null : _removeSelectedImage,
              onClear: _isSubmitting ? null : _clearSelectedImages,
            ),
            if (_formError != null) ...[
              const SizedBox(height: AppSpacing.lg),
              _FormFeedbackPanel(message: _formError!, isError: true),
            ],
            if (_lastResult != null) ...[
              const SizedBox(height: AppSpacing.lg),
              _RegistrationResultPanel(result: _lastResult!),
            ],
            const SizedBox(height: AppSpacing.lg),
            FilledButton.icon(
              onPressed: _canSubmit ? _registerMember : null,
              icon: _isSubmitting
                  ? const SizedBox.square(
                      dimension: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : Icon(Icons.save_outlined),
              label: Text(_isSubmitting ? 'Registering...' : 'Register'),
            ),
          ],
        ),
      ),
    );
    return AppPage(
      maxWidth: AppLayout.formMaxWidth,
      alignment: Alignment.topCenter,
      children: [
        const HeaderBlock(
          title: 'Register',
          subtitle: 'Add known people using clear face images.',
          icon: Icons.person_add_alt_1,
        ),
        const SizedBox(height: AppSpacing.lg),
        formCard,
      ],
    );
  }
}

class _RegistrationResultPanel extends StatelessWidget {
  const _RegistrationResultPanel({required this.result});

  final RegisterMemberResult result;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.surfaceSubtle,
        border: Border.all(color: AppColors.border),
        borderRadius: BorderRadius.circular(AppRadii.sm),
      ),
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.md),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              result.message,
              style: textTheme.bodyMedium?.copyWith(
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: AppSpacing.sm),
            _ResultCountRow(
              acceptedCount: result.acceptedImages.length,
              rejectedCount: result.rejectedImages.length,
            ),
            if (result.rejectedImages.isNotEmpty) ...[
              const SizedBox(height: AppSpacing.md),
              ...result.rejectedImages.map(
                (image) => _RejectedImageReason(image: image),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _ResultCountRow extends StatelessWidget {
  const _ResultCountRow({
    required this.acceptedCount,
    required this.rejectedCount,
  });

  final int acceptedCount;
  final int rejectedCount;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: AppSpacing.sm,
      runSpacing: AppSpacing.sm,
      children: [
        StatusBadge(
          icon: Icons.check_circle_outline,
          label: '$acceptedCount accepted',
          tone: StatusBadgeTone.success,
        ),
        StatusBadge(
          icon: Icons.error_outline,
          label: '$rejectedCount rejected',
          tone: rejectedCount == 0
              ? StatusBadgeTone.neutral
              : StatusBadgeTone.warning,
        ),
      ],
    );
  }
}

class _RejectedImageReason extends StatelessWidget {
  const _RejectedImageReason({required this.image});

  final RegistrationImageResult image;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(
            Icons.warning_amber_outlined,
            size: 18,
            color: AppColors.warning,
          ),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Text(
              '${image.filename}: ${image.reason}',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ),
        ],
      ),
    );
  }
}

class _FormFeedbackPanel extends StatelessWidget {
  const _FormFeedbackPanel({required this.message, required this.isError});

  final String message;
  final bool isError;

  @override
  Widget build(BuildContext context) {
    final color = isError ? AppColors.danger : AppColors.success;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: color.withAlpha(18),
        border: Border.all(color: color.withAlpha(72)),
        borderRadius: BorderRadius.circular(AppRadii.sm),
      ),
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.md),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(
              isError ? Icons.error_outline : Icons.check_circle_outline,
              color: color,
              size: 20,
            ),
            const SizedBox(width: AppSpacing.sm),
            Expanded(
              child: Text(
                message,
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                      color: color,
                      fontWeight: FontWeight.w700,
                    ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ImagePickerPanel extends StatelessWidget {
  const _ImagePickerPanel({
    required this.images,
    required this.submitting,
    required this.onPick,
    required this.onRemove,
    required this.onClear,
  });

  final List<PlatformFile> images;
  final bool submitting;
  final VoidCallback onPick;
  final ValueChanged<int>? onRemove;
  final VoidCallback? onClear;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final totalBytes = images.fold<int>(0, (sum, image) => sum + image.size);

    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.surfaceSubtle,
        border: Border.all(
          color: images.isEmpty ? AppColors.borderStrong : AppColors.tealMuted,
        ),
        borderRadius: BorderRadius.circular(AppRadii.sm),
      ),
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Container(
                  width: 44,
                  height: 44,
                  decoration: BoxDecoration(
                    color: AppColors.tealSoft,
                    borderRadius: BorderRadius.circular(AppRadii.sm),
                  ),
                  child: Icon(
                    Icons.add_photo_alternate_outlined,
                    color: AppColors.teal,
                  ),
                ),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Face images',
                        style: textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.w900,
                        ),
                      ),
                      const SizedBox(height: AppSpacing.xs),
                      Text(
                        'Use clear JPG, PNG, or WebP images with one visible face per photo.',
                        style: textTheme.bodyMedium?.copyWith(
                          color: AppColors.textMuted,
                          height: 1.35,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
            const SizedBox(height: AppSpacing.lg),
            OutlinedButton.icon(
              onPressed: submitting ? null : onPick,
              icon: Icon(Icons.upload_file_outlined),
              label: Text(
                images.isEmpty ? 'Choose face images' : 'Replace images',
              ),
            ),
            const SizedBox(height: AppSpacing.md),
            if (images.isEmpty)
              _NoImagesSelectedHint(disabled: submitting)
            else ...[
              Wrap(
                spacing: AppSpacing.sm,
                runSpacing: AppSpacing.sm,
                children: [
                  StatusBadge(
                    icon: Icons.image_outlined,
                    label:
                        '${images.length} image${images.length == 1 ? '' : 's'} selected',
                    tone: StatusBadgeTone.success,
                  ),
                  StatusBadge(
                    icon: Icons.storage_outlined,
                    label: _formatBytes(totalBytes),
                  ),
                ],
              ),
              const SizedBox(height: AppSpacing.md),
              LayoutBuilder(
                builder: (context, constraints) {
                  final tileWidth =
                      constraints.maxWidth >= AppBreakpoints.compact
                          ? 142.0
                          : 118.0;
                  return Wrap(
                    spacing: AppSpacing.md,
                    runSpacing: AppSpacing.md,
                    children: images.asMap().entries.map((entry) {
                      return _SelectedImageTile(
                        image: entry.value,
                        width: tileWidth,
                        onRemove: onRemove == null
                            ? null
                            : () => onRemove!(entry.key),
                      );
                    }).toList(),
                  );
                },
              ),
              const SizedBox(height: AppSpacing.md),
              Align(
                alignment: Alignment.centerLeft,
                child: TextButton.icon(
                  onPressed: onClear,
                  icon: Icon(Icons.clear_all),
                  label: Text('Clear selection'),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  static String _formatBytes(int bytes) {
    if (bytes < 1024) return '$bytes B';
    final kb = bytes / 1024;
    if (kb < 1024) return '${kb.toStringAsFixed(1)} KB';
    return '${(kb / 1024).toStringAsFixed(1)} MB';
  }
}

class _NoImagesSelectedHint extends StatelessWidget {
  const _NoImagesSelectedHint({required this.disabled});

  final bool disabled;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.surface,
        border: Border.all(color: AppColors.border),
        borderRadius: BorderRadius.circular(AppRadii.sm),
      ),
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Column(
          children: [
            Icon(
              Icons.image_search_outlined,
              color: disabled ? AppColors.textSubtle : AppColors.textMuted,
              size: 36,
            ),
            const SizedBox(height: AppSpacing.sm),
            Text(
              'No images selected',
              style: Theme.of(
                context,
              ).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: AppSpacing.xs),
            Text(
              'Choose at least one face image before registering.',
              textAlign: TextAlign.center,
              style: Theme.of(
                context,
              ).textTheme.bodySmall?.copyWith(color: AppColors.textMuted),
            ),
          ],
        ),
      ),
    );
  }
}

class _SelectedImageTile extends StatelessWidget {
  const _SelectedImageTile({
    required this.image,
    required this.width,
    required this.onRemove,
  });

  final PlatformFile image;
  final double width;
  final VoidCallback? onRemove;

  @override
  Widget build(BuildContext context) {
    final preview = image.bytes == null
        ? Container(
            color: AppColors.tealSoft,
            child: Icon(Icons.image_outlined, color: AppColors.teal),
          )
        : Image.memory(image.bytes!, fit: BoxFit.cover, gaplessPlayback: true);

    return SizedBox(
      width: width,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: AppColors.surface,
          border: Border.all(color: AppColors.border),
          borderRadius: BorderRadius.circular(AppRadii.sm),
        ),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(AppRadii.sm),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Stack(
                children: [
                  AspectRatio(aspectRatio: 1, child: preview),
                  Positioned(
                    top: AppSpacing.xs,
                    right: AppSpacing.xs,
                    child: IconButton.filledTonal(
                      visualDensity: VisualDensity.compact,
                      onPressed: onRemove,
                      icon: Icon(Icons.close, size: 16),
                      tooltip: context.tr('Remove image'),
                    ),
                  ),
                ],
              ),
              Padding(
                padding: const EdgeInsets.all(AppSpacing.sm),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      image.name,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.labelMedium?.copyWith(
                            fontWeight: FontWeight.w800,
                          ),
                    ),
                    const SizedBox(height: AppSpacing.xs),
                    Text(
                      _formatBytes(image.size),
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                            color: AppColors.textMuted,
                          ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  static String _formatBytes(int bytes) {
    if (bytes < 1024) return '$bytes B';
    final kb = bytes / 1024;
    if (kb < 1024) return '${kb.toStringAsFixed(1)} KB';
    return '${(kb / 1024).toStringAsFixed(1)} MB';
  }
}
