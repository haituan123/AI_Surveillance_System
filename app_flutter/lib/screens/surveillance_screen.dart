import 'dart:async';
import 'dart:math' as math;
import 'dart:typed_data';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart' hide Text;

import '../core/app_localization.dart';
import '../models/security_models.dart';
import '../services/security_service.dart';
import '../theme/app_tokens.dart';
import '../widgets/app_message.dart';
import '../widgets/app_page.dart';
import '../widgets/empty_panel.dart';
import '../widgets/header_block.dart';
import '../widgets/localized_text.dart';
import '../widgets/status_badge.dart';

enum _SurveillanceMode { live, uploadedVideo }

class SurveillanceScreen extends StatefulWidget {
  const SurveillanceScreen({super.key, this.service});

  final SecurityService? service;

  @override
  State<SurveillanceScreen> createState() => _SurveillanceScreenState();
}

class _SurveillanceScreenState extends State<SurveillanceScreen> {
  late final SecurityService _service = widget.service ?? SecurityService();
  late final TextEditingController _zoneNameController =
      TextEditingController();
  _SurveillanceMode _mode = _SurveillanceMode.live;
  List<CameraModel> _cameras = const [];
  int? _selectedCameraId;
  SurveillanceStatusModel? _liveStatus;
  LatestAnalysisModel? _latest;
  List<ZoneModel> _zones = const [];
  List<ZonePointModel> _draftZonePoints = const [];
  Uint8List? _frame;
  VideoAnalysisStatusModel? _videoStatus;
  VideoAnalysisResultsModel? _videoResults;
  Timer? _liveTimer;
  Timer? _videoTimer;
  bool _livePollInFlight = false;
  bool _videoPollInFlight = false;
  int _livePollFailures = 0;
  int _videoPollFailures = 0;
  bool _busy = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadLive();
  }

  @override
  void dispose() {
    _liveTimer?.cancel();
    _videoTimer?.cancel();
    _zoneNameController.dispose();
    super.dispose();
  }

  Future<void> _loadLive() async {
    await _guard(() async {
      final values = await Future.wait([
        _service.listCameras(),
        _service.surveillanceStatus(),
      ]);
      final cameras = values[0] as List<CameraModel>;
      final status = values[1] as SurveillanceStatusModel;
      final selectedCameraId = status.cameraId ??
          _selectedCameraId ??
          (cameras.isEmpty ? null : cameras.first.id);
      final zones = selectedCameraId == null
          ? const <ZoneModel>[]
          : await _service.listZones(selectedCameraId);
      if (!mounted) return;
      setState(() {
        _cameras = cameras;
        _liveStatus = status;
        _selectedCameraId = selectedCameraId;
        _zones = zones;
        _draftZonePoints = const [];
      });
      if (status.running) _startLivePolling();
    });
  }

  Future<void> _addWebcam() async {
    await _guard(() async {
      final camera = await _service.addLaptopWebcam();
      final cameras = await _service.listCameras();
      if (!mounted) return;
      setState(() {
        _cameras = cameras;
        _selectedCameraId = camera.id;
        _zones = const [];
        _draftZonePoints = const [];
      });
      await _loadZones(camera.id);
      if (mounted) {
        showAppSnackBar(
          context,
          message: 'Laptop webcam added.',
          tone: AppMessageTone.success,
        );
      }
    });
  }

  Future<void> _startLive() async {
    final cameraId = _selectedCameraId;
    if (cameraId == null) return;
    await _guard(() async {
      final status = await _service.startSurveillance(cameraId);
      if (!mounted) return;
      setState(() {
        _liveStatus = status;
        _latest = null;
      });
      _startLivePolling();
      showAppSnackBar(
        context,
        message: 'Live surveillance started.',
        tone: AppMessageTone.success,
      );
    });
  }

  Future<void> _loadZones(int cameraId) async {
    try {
      final zones = await _service.listZones(cameraId);
      if (!mounted) return;
      setState(() => _zones = zones);
    } catch (error) {
      if (mounted) setState(() => _error = friendlyErrorMessage(error));
    }
  }

  void _selectCamera(int? cameraId) {
    setState(() {
      _selectedCameraId = cameraId;
      _zones = const [];
      _draftZonePoints = const [];
    });
    if (cameraId != null) _loadZones(cameraId);
  }

  void _addDraftZonePoint(ZonePointModel point) {
    if (_mode != _SurveillanceMode.live) return;
    if (_liveStatus?.running != true) return;
    if (_draftZonePoints.length >= 4) return;
    setState(() {
      _draftZonePoints = [..._draftZonePoints, point];
    });
  }

  void _undoDraftZonePoint() {
    if (_draftZonePoints.isEmpty) return;
    setState(() {
      _draftZonePoints =
          _draftZonePoints.take(_draftZonePoints.length - 1).toList();
    });
  }

  void _clearDraftZone() {
    if (_draftZonePoints.isEmpty) return;
    setState(() => _draftZonePoints = const []);
  }

  Future<void> _saveDraftZone() async {
    final cameraId = _selectedCameraId;
    if (cameraId == null || _draftZonePoints.length != 4) return;
    final name = _zoneNameController.text.trim();
    if (name.isEmpty) {
      setState(() => _error = 'Zone name is required.');
      return;
    }
    await _guard(() async {
      await _service.createZone(
        cameraId: cameraId,
        name: name,
        points: _draftZonePoints,
      );
      final zones = await _service.listZones(cameraId);
      if (!mounted) return;
      setState(() {
        _zones = zones;
        _draftZonePoints = const [];
        _zoneNameController.clear();
      });
      showAppSnackBar(
        context,
        message: 'Restricted zone saved.',
        tone: AppMessageTone.success,
      );
    });
  }

  Future<void> _deleteZone(int zoneId) async {
    final cameraId = _selectedCameraId;
    if (cameraId == null) return;
    await _guard(() async {
      await _service.deleteZone(zoneId);
      final zones = await _service.listZones(cameraId);
      if (!mounted) return;
      setState(() => _zones = zones);
      showAppSnackBar(
        context,
        message: 'Restricted zone deleted.',
        tone: AppMessageTone.info,
      );
    });
  }

  Future<void> _setZoneActive(ZoneModel zone, bool isActive) async {
    final cameraId = _selectedCameraId;
    if (cameraId == null) return;
    await _guard(() async {
      await _service.setZoneActive(zone.id, isActive);
      final zones = await _service.listZones(cameraId);
      if (!mounted) return;
      setState(() => _zones = zones);
    });
  }

  Future<void> _stopLive() async {
    await _guard(() async {
      final status = await _service.stopSurveillance();
      _liveTimer?.cancel();
      if (!mounted) return;
      setState(() {
        _liveStatus = status;
        _latest = null;
        _frame = null;
      });
      showAppSnackBar(
        context,
        message: 'Live surveillance stopped.',
        tone: AppMessageTone.info,
      );
    });
  }

  void _startLivePolling() {
    _liveTimer?.cancel();
    _pollLive();
    _liveTimer = Timer.periodic(
      const Duration(milliseconds: 700),
      (_) => _pollLive(),
    );
  }

  Future<void> _pollLive() async {
    if (_livePollInFlight) return;
    _livePollInFlight = true;
    try {
      final status = await _service.surveillanceStatus();
      LatestAnalysisModel? latest;
      Uint8List? frame;
      if (status.running) {
        latest = await _service.latestAnalysis();
        frame = await _service.liveFrame();
      }
      if (!mounted) return;
      setState(() {
        _livePollFailures = 0;
        _liveStatus = status;
        if (latest != null) {
          _latest = latest;
        }
        if (frame != null) _frame = frame;
        if (!status.running) {
          _latest = null;
          _frame = null;
        }
      });
      if (!status.running) _liveTimer?.cancel();
    } catch (error) {
      if (mounted) {
        _livePollFailures += 1;
        if (_livePollFailures >= 3) {
          setState(() => _error = friendlyErrorMessage(error));
        }
      }
    } finally {
      _livePollInFlight = false;
    }
  }

  Future<void> _pickAndAnalyze() async {
    final FilePickerResult? picked;
    try {
      picked = await FilePicker.platform.pickFiles(
        type: FileType.custom,
        allowedExtensions: const ['mp4', 'avi', 'mov', 'mkv', 'webm'],
        withReadStream: true,
      );
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = friendlyErrorMessage(error));
      return;
    }
    final file = picked?.files.single;
    if (file == null) return;
    if (file.readStream == null && file.bytes == null && file.path == null) {
      setState(() => _error = 'The selected video data is not available.');
      return;
    }
    await _guard(() async {
      final status = await _service.submitVideo(
        path: file.path,
        stream: file.readStream,
        length: file.size,
        bytes: file.bytes,
        filename: file.name,
      );
      if (!mounted) return;
      setState(() {
        _videoStatus = status;
        _videoResults = null;
        _frame = null;
      });
      _startVideoPolling();
      showAppSnackBar(
        context,
        message: 'Video analysis submitted.',
        tone: AppMessageTone.success,
      );
    });
  }

  void _startVideoPolling() {
    _videoTimer?.cancel();
    _pollVideo();
    _videoTimer = Timer.periodic(
      const Duration(milliseconds: 700),
      (_) => _pollVideo(),
    );
  }

  Future<void> _pollVideo() async {
    if (_videoPollInFlight) return;
    final jobId = _videoStatus?.jobId;
    if (jobId == null) return;
    _videoPollInFlight = true;
    try {
      final status = await _service.videoStatus(jobId);
      VideoAnalysisResultsModel? results;
      try {
        results = await _service.videoResults(jobId);
      } on ApiException catch (error) {
        if (error.statusCode != 404) rethrow;
      }
      final frame = await _service.videoFrame(jobId);
      if (!mounted) return;
      setState(() {
        _videoPollFailures = 0;
        _videoStatus = status;
        if (results != null) _videoResults = results;
        if (frame != null) _frame = frame;
        if (status.errorMessage != null && status.errorMessage!.isNotEmpty) {
          _error = friendlyErrorMessage(status.errorMessage!);
        }
      });
      if (!status.isActive) _videoTimer?.cancel();
    } catch (error) {
      if (mounted) {
        _videoPollFailures += 1;
        if (_videoPollFailures >= 3) {
          setState(() => _error = friendlyErrorMessage(error));
        }
      }
    } finally {
      _videoPollInFlight = false;
    }
  }

  Future<void> _deleteVideo() async {
    final jobId = _videoStatus?.jobId;
    if (jobId == null) return;
    await _guard(() async {
      await _service.deleteVideoJob(jobId);
      _videoTimer?.cancel();
      if (!mounted) return;
      setState(() {
        _videoStatus = null;
        _videoResults = null;
        _frame = null;
      });
      showAppSnackBar(
        context,
        message: 'Video analysis cleared.',
        tone: AppMessageTone.info,
      );
    });
  }

  Future<void> _guard(Future<void> Function() operation) async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await operation();
    } catch (error) {
      if (mounted) setState(() => _error = friendlyErrorMessage(error));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _setMode(Set<_SurveillanceMode> value) {
    setState(() => _mode = value.single);
  }

  @override
  Widget build(BuildContext context) {
    final showLive = _mode == _SurveillanceMode.live;

    return AppPage(
      maxWidth: AppLayout.dataMaxWidth,
      children: [
        HeaderBlock(
          title: 'Surveillance',
          subtitle:
              'Monitor the live webcam or analyze a temporary uploaded video.',
          icon: Icons.videocam,
        ),
        const SizedBox(height: AppSpacing.lg),
        if (_error != null)
          _ErrorBanner(
            message: _error!,
            onDismiss: () => setState(() => _error = null),
            onRetry: showLive ? _loadLive : null,
          ),
        if (_error != null) const SizedBox(height: AppSpacing.lg),
        LayoutBuilder(
          builder: (context, constraints) {
            final preview = _SurveillancePreviewCard(
              mode: _mode,
              frame: _frame,
              busy: _busy,
              liveStatus: _liveStatus,
              latest: _latest,
              videoStatus: _videoStatus,
              hasCameras: _cameras.isNotEmpty,
              error: _error,
              draftZonePoints: _draftZonePoints,
              onAddZonePoint: _addDraftZonePoint,
            );
            final sidePanel = showLive ? _buildLivePanel() : _buildVideoPanel();

            if (constraints.maxWidth < AppBreakpoints.desktop) {
              return Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  _ModeSelector(mode: _mode, onChanged: _setMode),
                  const SizedBox(height: AppSpacing.md),
                  sidePanel,
                  const SizedBox(height: AppSpacing.md),
                  preview,
                ],
              );
            }

            return Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  flex: 7,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      _ModeSelector(mode: _mode, onChanged: _setMode),
                      const SizedBox(height: AppSpacing.md),
                      preview,
                    ],
                  ),
                ),
                const SizedBox(width: AppSpacing.lg),
                Expanded(flex: 4, child: sidePanel),
              ],
            );
          },
        ),
      ],
    );
  }

  Widget _buildLivePanel() {
    final running = _liveStatus?.running ?? false;
    final failed = _liveStatus?.state == 'failed';
    final liveError = _liveStatus?.errorMessage;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Card(
          child: Padding(
            padding: const EdgeInsets.all(AppSpacing.lg),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(
                  'Camera controls',
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.w900,
                        color: AppColors.text,
                      ),
                ),
                const SizedBox(height: AppSpacing.md),
                if (_cameras.isNotEmpty)
                  DropdownButtonFormField<int>(
                    initialValue: _selectedCameraId,
                    decoration: InputDecoration(
                      labelText: context.tr('Camera'),
                      prefixIcon: Icon(Icons.videocam_outlined),
                    ),
                    items: _cameras
                        .map(
                          (camera) => DropdownMenuItem(
                            value: camera.id,
                            child: Text(camera.name),
                          ),
                        )
                        .toList(),
                    onChanged: running ? null : _selectCamera,
                  )
                else
                  _UnavailablePanel(
                    icon: Icons.no_photography_outlined,
                    title: 'No camera configured',
                    message:
                        'Add the laptop webcam before starting live surveillance.',
                    action: OutlinedButton.icon(
                      onPressed: _busy ? null : _addWebcam,
                      icon: Icon(Icons.add_a_photo_outlined),
                      label: Text('Add laptop webcam'),
                    ),
                  ),
                const SizedBox(height: AppSpacing.lg),
                Row(
                  children: [
                    Expanded(
                      child: FilledButton.icon(
                        onPressed:
                            !_busy && !running && _selectedCameraId != null
                                ? _startLive
                                : null,
                        icon: Icon(Icons.play_arrow),
                        label: Text('Start'),
                      ),
                    ),
                    const SizedBox(width: AppSpacing.md),
                    Expanded(
                      child: OutlinedButton.icon(
                        onPressed: !_busy && running ? _stopLive : null,
                        icon: Icon(Icons.stop),
                        label: Text('Stop'),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
        if (failed && liveError != null && liveError.isNotEmpty) ...[
          const SizedBox(height: AppSpacing.md),
          _UnavailablePanel(
            icon: Icons.error_outline,
            title: 'Camera unavailable',
            message: liveError,
            action: OutlinedButton.icon(
              onPressed: _busy ? null : _loadLive,
              icon: Icon(Icons.refresh),
              label: Text('Retry camera'),
            ),
          ),
        ],
        const SizedBox(height: AppSpacing.md),
        _RestrictedZonePanel(
          running: running,
          zones: _zones,
          draftPoints: _draftZonePoints,
          nameController: _zoneNameController,
          onSave: _busy || _draftZonePoints.length != 4 ? null : _saveDraftZone,
          onUndo:
              _busy || _draftZonePoints.isEmpty ? null : _undoDraftZonePoint,
          onClear: _busy || _draftZonePoints.isEmpty ? null : _clearDraftZone,
          onToggleActive: _busy ? null : _setZoneActive,
          onDelete: _busy ? null : _deleteZone,
        ),
        const SizedBox(height: AppSpacing.md),
        _LiveDetectionSummary(latest: _latest),
      ],
    );
  }

  Widget _buildVideoPanel() {
    final status = _videoStatus;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Card(
          child: Padding(
            padding: const EdgeInsets.all(AppSpacing.lg),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(
                  'Uploaded video',
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.w900,
                        color: AppColors.text,
                      ),
                ),
                const SizedBox(height: AppSpacing.xs),
                Text(
                  'Temporary mode: events and frames are not saved to history.',
                  style: Theme.of(
                    context,
                  ).textTheme.bodyMedium?.copyWith(color: AppColors.textMuted),
                ),
                const SizedBox(height: AppSpacing.lg),
                FilledButton.icon(
                  onPressed: !_busy && status == null ? _pickAndAnalyze : null,
                  icon: Icon(Icons.upload_file),
                  label: Text('Choose video'),
                ),
                const SizedBox(height: AppSpacing.sm),
                OutlinedButton.icon(
                  onPressed: !_busy && status != null ? _deleteVideo : null,
                  icon: Icon(
                    status?.isActive == true
                        ? Icons.cancel
                        : Icons.delete_outline,
                  ),
                  label: Text(
                    status?.isActive == true
                        ? 'Cancel analysis'
                        : 'Clear result',
                  ),
                ),
                if (status != null) ...[
                  const SizedBox(height: AppSpacing.lg),
                  _VideoStatusDetails(status: status),
                ],
              ],
            ),
          ),
        ),
        const SizedBox(height: AppSpacing.md),
        _VideoDetectionSummary(results: _videoResults),
      ],
    );
  }
}

class _ModeSelector extends StatelessWidget {
  const _ModeSelector({required this.mode, required this.onChanged});

  final _SurveillanceMode mode;
  final ValueChanged<Set<_SurveillanceMode>> onChanged;

  @override
  Widget build(BuildContext context) {
    return SegmentedButton<_SurveillanceMode>(
      segments: const [
        ButtonSegment(
          value: _SurveillanceMode.live,
          icon: Icon(Icons.videocam),
          label: Text('Live webcam'),
        ),
        ButtonSegment(
          value: _SurveillanceMode.uploadedVideo,
          icon: Icon(Icons.video_file),
          label: Text('Upload video'),
        ),
      ],
      selected: {mode},
      onSelectionChanged: onChanged,
    );
  }
}

class _SurveillancePreviewCard extends StatelessWidget {
  const _SurveillancePreviewCard({
    required this.mode,
    required this.frame,
    required this.busy,
    required this.liveStatus,
    required this.latest,
    required this.videoStatus,
    required this.hasCameras,
    required this.error,
    required this.draftZonePoints,
    required this.onAddZonePoint,
  });

  final _SurveillanceMode mode;
  final Uint8List? frame;
  final bool busy;
  final SurveillanceStatusModel? liveStatus;
  final LatestAnalysisModel? latest;
  final VideoAnalysisStatusModel? videoStatus;
  final bool hasCameras;
  final String? error;
  final List<ZonePointModel> draftZonePoints;
  final ValueChanged<ZonePointModel> onAddZonePoint;

  @override
  Widget build(BuildContext context) {
    final isLive = mode == _SurveillanceMode.live;
    final running = liveStatus?.running == true;
    final failed = liveStatus?.state == 'failed';
    final overlay = _overlayFor(
      isLive: isLive,
      running: running,
      failed: failed,
      hasCameras: hasCameras,
    );

    return Card(
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.all(AppSpacing.lg),
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    isLive ? 'Camera preview' : 'Video preview',
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.w900,
                          color: AppColors.text,
                        ),
                  ),
                ),
                StatusBadge(
                  label: isLive
                      ? running
                          ? '${liveStatus!.fps.toStringAsFixed(1)} FPS'
                          : failed
                              ? 'Unavailable'
                              : 'Stopped'
                      : videoStatus?.state ?? 'No video',
                  icon: isLive
                      ? running
                          ? Icons.sensors
                          : failed
                              ? Icons.error_outline
                              : Icons.videocam_off_outlined
                      : Icons.movie_outlined,
                  tone: running || videoStatus?.isActive == true
                      ? StatusBadgeTone.success
                      : failed || error != null
                          ? StatusBadgeTone.danger
                          : StatusBadgeTone.neutral,
                ),
              ],
            ),
          ),
          AspectRatio(
            aspectRatio: 16 / 9,
            child: ColoredBox(
              color: AppColors.cameraCanvas,
              child: Stack(
                fit: StackFit.expand,
                children: [
                  if (frame != null)
                    Image.memory(
                      frame!,
                      fit: BoxFit.contain,
                      gaplessPlayback: true,
                    ),
                  if (isLive && running && latest != null)
                    _ZoneDraftOverlay(
                      frameWidth: latest!.width,
                      frameHeight: latest!.height,
                      points: draftZonePoints,
                      onAddPoint: onAddZonePoint,
                    ),
                  if (frame == null || overlay != null)
                    _PreviewOverlay(
                      icon: overlay?.icon ?? Icons.videocam_off,
                      title: overlay?.title ?? 'Waiting for frame',
                      message: overlay?.message ??
                          'A preview frame will appear when analysis produces one.',
                      busy: busy,
                    ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  _PreviewOverlayData? _overlayFor({
    required bool isLive,
    required bool running,
    required bool failed,
    required bool hasCameras,
  }) {
    if (error != null) {
      return const _PreviewOverlayData(
        icon: Icons.cloud_off_outlined,
        title: 'Backend unavailable',
        message: 'Check the backend connection and retry.',
      );
    }
    if (isLive && !hasCameras) {
      return const _PreviewOverlayData(
        icon: Icons.no_photography_outlined,
        title: 'No camera configured',
        message: 'Add the laptop webcam to enable live preview.',
      );
    }
    if (isLive && failed) {
      return const _PreviewOverlayData(
        icon: Icons.error_outline,
        title: 'Camera unavailable',
        message: 'The selected camera could not provide frames.',
      );
    }
    if (isLive && !running) {
      return const _PreviewOverlayData(
        icon: Icons.videocam_off_outlined,
        title: 'Camera stopped',
        message: 'Start surveillance to show the live camera feed.',
      );
    }
    if (!isLive && videoStatus == null) {
      return const _PreviewOverlayData(
        icon: Icons.video_file_outlined,
        title: 'No video selected',
        message: 'Choose a video to begin temporary analysis.',
      );
    }
    if (!isLive && videoStatus?.isActive == true && frame == null) {
      return const _PreviewOverlayData(
        icon: Icons.hourglass_top,
        title: 'Preparing preview',
        message: 'Frames will appear as the uploaded video is processed.',
      );
    }
    return null;
  }
}

class _PreviewOverlayData {
  const _PreviewOverlayData({
    required this.icon,
    required this.title,
    required this.message,
  });

  final IconData icon;
  final String title;
  final String message;
}

class _PreviewOverlay extends StatelessWidget {
  const _PreviewOverlay({
    required this.icon,
    required this.title,
    required this.message,
    required this.busy,
  });

  final IconData icon;
  final String title;
  final String message;
  final bool busy;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final compact = constraints.maxHeight < 260;
        return Container(
          color: AppColors.cameraCanvas.withAlpha(220),
          child: Center(
            child: SingleChildScrollView(
              padding: EdgeInsets.all(compact ? AppSpacing.md : AppSpacing.xl),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  if (busy)
                    SizedBox.square(
                      dimension: compact ? 32 : 42,
                      child: const CircularProgressIndicator(strokeWidth: 3),
                    )
                  else
                    Icon(icon, color: Colors.white70, size: compact ? 38 : 56),
                  SizedBox(height: compact ? AppSpacing.sm : AppSpacing.lg),
                  Text(
                    title,
                    textAlign: TextAlign.center,
                    maxLines: compact ? 1 : 2,
                    overflow: TextOverflow.ellipsis,
                    style: (compact
                            ? Theme.of(context).textTheme.titleMedium
                            : Theme.of(context).textTheme.titleLarge)
                        ?.copyWith(
                      color: Colors.white,
                      fontWeight: FontWeight.w900,
                    ),
                  ),
                  const SizedBox(height: AppSpacing.xs),
                  Text(
                    message,
                    textAlign: TextAlign.center,
                    maxLines: compact ? 2 : 3,
                    overflow: TextOverflow.ellipsis,
                    style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                          color: Colors.white70,
                          height: 1.25,
                        ),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }
}

class _VideoStatusDetails extends StatelessWidget {
  const _VideoStatusDetails({required this.status});

  final VideoAnalysisStatusModel status;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          status.filename,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: Theme.of(
            context,
          ).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w900),
        ),
        const SizedBox(height: AppSpacing.sm),
        LinearProgressIndicator(value: status.progress?.clamp(0, 1)),
        const SizedBox(height: AppSpacing.sm),
        Wrap(
          spacing: AppSpacing.sm,
          runSpacing: AppSpacing.sm,
          children: [
            StatusBadge(icon: Icons.timelapse, label: status.state),
            StatusBadge(
              icon: Icons.filter_frames_outlined,
              label: '${status.processedFrames} frames',
            ),
            StatusBadge(
              icon: Icons.speed,
              label: '${status.processingFps.toStringAsFixed(1)} FPS',
            ),
          ],
        ),
        if (status.errorMessage != null && status.errorMessage!.isNotEmpty) ...[
          const SizedBox(height: AppSpacing.md),
          Text(
            status.errorMessage!,
            style: TextStyle(
              color: Theme.of(context).colorScheme.error,
              fontWeight: FontWeight.w700,
            ),
          ),
        ],
      ],
    );
  }
}

class _LiveDetectionSummary extends StatelessWidget {
  const _LiveDetectionSummary({required this.latest});

  final LatestAnalysisModel? latest;

  @override
  Widget build(BuildContext context) {
    final tracks = latest?.tracks ?? const <AnalysisTrackModel>[];
    final unknownLabels = _LiveUnknownPersonLabels(tracks);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              'Last detection',
              style: Theme.of(context).textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.w900,
                    color: AppColors.text,
                  ),
            ),
            const SizedBox(height: AppSpacing.md),
            if (tracks.isEmpty)
              const EmptyPanel(
                icon: Icons.face_retouching_off_outlined,
                title: 'No live detection result',
                message:
                    'Start the camera to see recognized and unknown people.',
                compact: true,
              )
            else
              ...tracks.map(
                (detection) => _DetectionTile(
                  detection,
                  title: unknownLabels.labelForDetection(detection),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _RestrictedZonePanel extends StatelessWidget {
  const _RestrictedZonePanel({
    required this.running,
    required this.zones,
    required this.draftPoints,
    required this.nameController,
    required this.onSave,
    required this.onUndo,
    required this.onClear,
    required this.onToggleActive,
    required this.onDelete,
  });

  final bool running;
  final List<ZoneModel> zones;
  final List<ZonePointModel> draftPoints;
  final TextEditingController nameController;
  final VoidCallback? onSave;
  final VoidCallback? onUndo;
  final VoidCallback? onClear;
  final void Function(ZoneModel zone, bool isActive)? onToggleActive;
  final ValueChanged<int>? onDelete;

  @override
  Widget build(BuildContext context) {
    final activeCount = zones.where((zone) => zone.isActive).length;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    'Restricted zones',
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.w900,
                          color: AppColors.text,
                        ),
                  ),
                ),
                StatusBadge(
                  icon: Icons.polyline_outlined,
                  label: '$activeCount active',
                ),
              ],
            ),
            const SizedBox(height: AppSpacing.sm),
            Text(
              running
                  ? 'Tap the live preview to place 4 corner points. Unknown people inside an active zone briefly will alert.'
                  : 'Start live surveillance before placing points.',
              style: Theme.of(
                context,
              ).textTheme.bodyMedium?.copyWith(color: AppColors.textMuted),
            ),
            const SizedBox(height: AppSpacing.md),
            TextField(
              controller: nameController,
              enabled: running,
              decoration: InputDecoration(
                labelText: context.tr('Zone name'),
                hintText: context.tr('Server door'),
                prefixIcon: Icon(Icons.edit_location_alt_outlined),
              ),
              textInputAction: TextInputAction.done,
            ),
            const SizedBox(height: AppSpacing.md),
            Wrap(
              spacing: AppSpacing.sm,
              runSpacing: AppSpacing.sm,
              children: [
                FilledButton.icon(
                  onPressed: onSave,
                  icon: Icon(Icons.save_outlined),
                  label: Text('Save ${draftPoints.length}/4 points'),
                ),
                OutlinedButton.icon(
                  onPressed: onUndo,
                  icon: Icon(Icons.undo),
                  label: Text('Undo'),
                ),
                OutlinedButton.icon(
                  onPressed: onClear,
                  icon: Icon(Icons.clear),
                  label: Text('Clear'),
                ),
              ],
            ),
            const SizedBox(height: AppSpacing.md),
            if (draftPoints.isNotEmpty)
              Wrap(
                spacing: AppSpacing.xs,
                runSpacing: AppSpacing.xs,
                children: draftPoints
                    .map(
                      (point) => Chip(
                        visualDensity: VisualDensity.compact,
                        label: Text('${point.x}, ${point.y}'),
                      ),
                    )
                    .toList(),
              ),
            if (zones.isNotEmpty) ...[
              if (draftPoints.isNotEmpty) const SizedBox(height: AppSpacing.md),
              ...zones.map(
                (zone) => ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: Checkbox(
                    value: zone.isActive,
                    onChanged: onToggleActive == null
                        ? null
                        : (value) => onToggleActive!(zone, value ?? false),
                  ),
                  title: Text(zone.name),
                  subtitle: Text(
                    zone.isActive
                        ? '${zone.points.length} points · active'
                        : '${zone.points.length} points · inactive',
                  ),
                  trailing: IconButton(
                    tooltip: context.tr('Delete zone'),
                    onPressed:
                        onDelete == null ? null : () => onDelete!(zone.id),
                    icon: Icon(Icons.delete_outline),
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _ZoneDraftOverlay extends StatelessWidget {
  const _ZoneDraftOverlay({
    required this.frameWidth,
    required this.frameHeight,
    required this.points,
    required this.onAddPoint,
  });

  final int frameWidth;
  final int frameHeight;
  final List<ZonePointModel> points;
  final ValueChanged<ZonePointModel> onAddPoint;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final imageRect = _containedImageRect(
          Size(constraints.maxWidth, constraints.maxHeight),
        );
        return GestureDetector(
          behavior: HitTestBehavior.translucent,
          onTapDown: (details) {
            final local = details.localPosition;
            if (!imageRect.contains(local)) return;
            final x =
                ((local.dx - imageRect.left) / imageRect.width * frameWidth)
                    .round()
                    .clamp(0, frameWidth)
                    .toInt();
            final y =
                ((local.dy - imageRect.top) / imageRect.height * frameHeight)
                    .round()
                    .clamp(0, frameHeight)
                    .toInt();
            onAddPoint(ZonePointModel(x: x, y: y));
          },
          child: CustomPaint(
            painter: _ZoneDraftPainter(
              imageRect: imageRect,
              frameWidth: frameWidth,
              frameHeight: frameHeight,
              points: points,
            ),
            size: Size.infinite,
          ),
        );
      },
    );
  }

  Rect _containedImageRect(Size canvas) {
    final scale = math.min(
      canvas.width / frameWidth,
      canvas.height / frameHeight,
    );
    final width = frameWidth * scale;
    final height = frameHeight * scale;
    return Rect.fromLTWH(
      (canvas.width - width) / 2,
      (canvas.height - height) / 2,
      width,
      height,
    );
  }
}

class _ZoneDraftPainter extends CustomPainter {
  const _ZoneDraftPainter({
    required this.imageRect,
    required this.frameWidth,
    required this.frameHeight,
    required this.points,
  });

  final Rect imageRect;
  final int frameWidth;
  final int frameHeight;
  final List<ZonePointModel> points;

  @override
  void paint(Canvas canvas, Size size) {
    if (points.isEmpty) return;
    final paint = Paint()
      ..color = Colors.amber
      ..strokeWidth = 2
      ..style = PaintingStyle.stroke;
    final fill = Paint()
      ..color = Colors.amber.withAlpha(45)
      ..style = PaintingStyle.fill;
    final dot = Paint()
      ..color = Colors.amber
      ..style = PaintingStyle.fill;
    final offsets = points.map(_toCanvas).toList();
    final path = Path()..moveTo(offsets.first.dx, offsets.first.dy);
    for (final offset in offsets.skip(1)) {
      path.lineTo(offset.dx, offset.dy);
    }
    if (offsets.length >= 3) {
      path.close();
      canvas.drawPath(path, fill);
    }
    canvas.drawPath(path, paint);
    for (var index = 0; index < offsets.length; index += 1) {
      canvas.drawCircle(offsets[index], 5, dot);
      _drawPointLabel(canvas, offsets[index], index + 1);
    }
  }

  Offset _toCanvas(ZonePointModel point) {
    return Offset(
      imageRect.left + point.x / frameWidth * imageRect.width,
      imageRect.top + point.y / frameHeight * imageRect.height,
    );
  }

  void _drawPointLabel(Canvas canvas, Offset offset, int index) {
    final painter = TextPainter(
      text: TextSpan(
        text: '$index',
        style: TextStyle(
          color: Colors.black,
          fontSize: 11,
          fontWeight: FontWeight.w800,
        ),
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    painter.paint(canvas, offset + const Offset(7, -16));
  }

  @override
  bool shouldRepaint(covariant _ZoneDraftPainter oldDelegate) {
    return oldDelegate.points != points ||
        oldDelegate.imageRect != imageRect ||
        oldDelegate.frameWidth != frameWidth ||
        oldDelegate.frameHeight != frameHeight;
  }
}

class _VideoDetectionSummary extends StatelessWidget {
  const _VideoDetectionSummary({required this.results});

  final VideoAnalysisResultsModel? results;

  @override
  Widget build(BuildContext context) {
    final events = results?.events ?? const <TemporaryVideoEventModel>[];
    final unknownLabels = _VideoUnknownPersonLabels(events);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              'Temporary events',
              style: Theme.of(context).textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.w900,
                    color: AppColors.text,
                  ),
            ),
            if (results != null) ...[
              const SizedBox(height: AppSpacing.sm),
              Wrap(
                spacing: AppSpacing.sm,
                runSpacing: AppSpacing.sm,
                children: [
                  StatusBadge(
                    icon: Icons.verified_user,
                    label: '${results!.knownEvents} known',
                    tone: StatusBadgeTone.success,
                  ),
                  StatusBadge(
                    icon: Icons.person_search,
                    label: '${results!.unknownEvents} unknown',
                    tone: StatusBadgeTone.warning,
                  ),
                ],
              ),
            ],
            const SizedBox(height: AppSpacing.md),
            if (events.isEmpty)
              const EmptyPanel(
                icon: Icons.manage_search,
                title: 'No temporary events',
                message: 'Choose a video to show analysis events here.',
                compact: true,
              )
            else
              ...events.reversed.map(
                (event) => _VideoEventTile(
                  event,
                  title: unknownLabels.labelForEvent(event),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _LiveUnknownPersonLabels {
  _LiveUnknownPersonLabels(List<AnalysisTrackModel> tracks) {
    for (final detection in tracks.where(
      (detection) => detection.status != 'known',
    )) {
      _labelsByDetection[detection] = format(detection.trackId);
    }
  }

  final Map<AnalysisTrackModel, String> _labelsByDetection = {};

  String labelForDetection(AnalysisTrackModel detection) {
    if (detection.status == 'known') {
      return detection.memberName ?? 'Known person';
    }
    return _labelsByDetection[detection] ?? 'Unknown Person';
  }

  static String format(int index) => _format(index);
}

class _VideoUnknownPersonLabels {
  _VideoUnknownPersonLabels(List<TemporaryVideoEventModel> events) {
    final unknownEvents =
        events.where((event) => event.status != 'known').toList()
          ..sort((a, b) {
            final timeComparison = a.timestampSeconds.compareTo(
              b.timestampSeconds,
            );
            if (timeComparison != 0) return timeComparison;
            return a.frameIndex.compareTo(b.frameIndex);
          });
    for (final entry in unknownEvents.indexed) {
      _labelsByEvent[entry.$2] = _format(entry.$1 + 1);
    }
  }

  final Map<TemporaryVideoEventModel, String> _labelsByEvent = {};

  String labelForEvent(TemporaryVideoEventModel event) {
    if (event.status == 'known') return event.memberName ?? 'Known person';
    return _labelsByEvent[event] ?? 'Unknown Person';
  }
}

String _format(int index) =>
    'Unknown Person ${index.toString().padLeft(2, '0')}';

class _DetectionTile extends StatelessWidget {
  const _DetectionTile(this.detection, {required this.title});

  final AnalysisTrackModel detection;
  final String title;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: ListTile(
        contentPadding: EdgeInsets.zero,
        leading: Icon(
          detection.status == 'known'
              ? Icons.verified_user
              : Icons.person_search,
        ),
        title: Text(title),
        subtitle: Text(
          '${((detection.similarity ?? detection.personConfidence) * 100).toStringAsFixed(1)}%',
        ),
        trailing: StatusBadge(
          label: detection.status,
          tone: detection.status == 'known'
              ? StatusBadgeTone.success
              : StatusBadgeTone.warning,
        ),
      ),
    );
  }
}

class _VideoEventTile extends StatelessWidget {
  const _VideoEventTile(this.event, {required this.title});

  final TemporaryVideoEventModel event;
  final String title;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: ListTile(
        contentPadding: EdgeInsets.zero,
        leading: Icon(
          event.status == 'known' ? Icons.verified_user : Icons.warning_amber,
        ),
        title: Text(title),
        subtitle: Text(
          '${event.timestampSeconds.toStringAsFixed(1)}s · '
          '${event.eventType.replaceAll('_', ' ')}',
        ),
        trailing: StatusBadge(
          label: event.status,
          tone: event.status == 'known'
              ? StatusBadgeTone.success
              : StatusBadgeTone.warning,
        ),
      ),
    );
  }
}

class _UnavailablePanel extends StatelessWidget {
  const _UnavailablePanel({
    required this.icon,
    required this.title,
    required this.message,
    this.action,
  });

  final IconData icon;
  final String title;
  final String message;
  final Widget? action;

  @override
  Widget build(BuildContext context) {
    return EmptyPanel(
      icon: icon,
      title: title,
      message: message,
      compact: true,
      action: action,
    );
  }
}

class _ErrorBanner extends StatelessWidget {
  const _ErrorBanner({
    required this.message,
    required this.onDismiss,
    required this.onRetry,
  });

  final String message;
  final VoidCallback onDismiss;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    return AppMessagePanel(
      title: message.toLowerCase().contains('permission')
          ? 'Permission needed'
          : 'Request failed',
      message: message,
      tone: message.toLowerCase().contains('permission')
          ? AppMessageTone.warning
          : AppMessageTone.danger,
      action: Wrap(
        spacing: AppSpacing.sm,
        runSpacing: AppSpacing.sm,
        children: [
          if (onRetry != null)
            OutlinedButton.icon(
              onPressed: onRetry,
              icon: Icon(Icons.refresh),
              label: Text('Retry'),
            ),
          TextButton(onPressed: onDismiss, child: Text('Dismiss')),
        ],
      ),
    );
  }
}
