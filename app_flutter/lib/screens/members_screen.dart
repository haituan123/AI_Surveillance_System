import 'package:flutter/material.dart' hide Text;

import '../core/app_localization.dart';
import '../core/timestamp_formatter.dart';
import '../models/member_model.dart';
import '../services/member_service.dart';
import '../theme/app_tokens.dart';
import '../widgets/app_message.dart';
import '../widgets/app_page.dart';
import '../widgets/empty_panel.dart';
import '../widgets/header_block.dart';
import '../widgets/localized_text.dart';
import '../widgets/section_header.dart';
import '../widgets/status_badge.dart';

class MembersScreen extends StatefulWidget {
  const MembersScreen({
    super.key,
    required this.refreshToken,
    required this.onMembersChanged,
  });

  final int refreshToken;
  final VoidCallback onMembersChanged;

  @override
  State<MembersScreen> createState() => _MembersScreenState();
}

class _MembersScreenState extends State<MembersScreen> {
  final MemberService _memberService = const MemberService();
  final TextEditingController _searchController = TextEditingController();
  final Set<int> _deletingMemberIds = {};

  late Future<List<MemberModel>> _membersFuture;
  String _query = '';

  @override
  void initState() {
    super.initState();
    _membersFuture = _memberService.listMembers();
    _searchController.addListener(_updateQuery);
  }

  @override
  void didUpdateWidget(covariant MembersScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.refreshToken != widget.refreshToken) {
      _refreshMembers();
    }
  }

  @override
  void dispose() {
    _searchController
      ..removeListener(_updateQuery)
      ..dispose();
    super.dispose();
  }

  void _updateQuery() {
    final nextQuery = _searchController.text.trim().toLowerCase();
    if (nextQuery == _query) return;
    setState(() => _query = nextQuery);
  }

  void _refreshMembers() {
    setState(() {
      _membersFuture = _memberService.listMembers();
    });
  }

  void _clearSearch() {
    _searchController.clear();
  }

  List<MemberModel> _filterMembers(List<MemberModel> members) {
    if (_query.isEmpty) return members;
    return members.where((member) {
      final registered = formatBackendTimestamp(member.createdAt).toLowerCase();
      return member.name.toLowerCase().contains(_query) ||
          member.imageCount.toString().contains(_query) ||
          registered.contains(_query);
    }).toList();
  }

  @override
  Widget build(BuildContext context) {
    return AppPage(
      maxWidth: AppLayout.dataMaxWidth,
      children: [
        HeaderBlock(
          title: 'Members',
          subtitle: 'Review registered people and manage saved face images.',
          icon: Icons.people_alt,
        ),
        const SizedBox(height: AppSpacing.lg),
        FutureBuilder<List<MemberModel>>(
          future: _membersFuture,
          builder: (context, snapshot) {
            if (snapshot.connectionState == ConnectionState.waiting) {
              return const _MembersLoadingState();
            }

            if (snapshot.hasError) {
              return _MembersErrorState(
                message: friendlyErrorMessage(
                  snapshot.error ?? 'Unknown error',
                ),
                onRetry: _refreshMembers,
              );
            }

            final members = snapshot.data ?? const [];
            final visibleMembers = _filterMembers(members);

            return Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                _MembersToolbar(
                  searchController: _searchController,
                  onClearSearch: _query.isEmpty ? null : _clearSearch,
                ),
                const SizedBox(height: AppSpacing.lg),
                const SectionHeader(title: 'Registered people'),
                if (members.isEmpty)
                  const EmptyPanel(
                    icon: Icons.people_outline,
                    title: 'No registered people',
                    message:
                        'Registered people will appear here after image registration.',
                  )
                else if (visibleMembers.isEmpty)
                  EmptyPanel(
                    icon: Icons.search_off,
                    title: 'No matching members',
                    message:
                        'No registered person matches the current search filter.',
                    action: OutlinedButton.icon(
                      onPressed: _clearSearch,
                      icon: Icon(Icons.clear),
                      label: Text('Clear search'),
                    ),
                  )
                else
                  _MembersList(
                    members: visibleMembers,
                    deletingMemberIds: _deletingMemberIds,
                    onDelete: _deleteMember,
                  ),
              ],
            );
          },
        ),
      ],
    );
  }

  Future<void> _deleteMember(MemberModel member) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) {
        return AlertDialog(
          icon: Icon(Icons.delete_outline, color: AppColors.danger),
          title: Text('Delete ${member.name}?'),
          content: Text(
            'This removes ${member.name} and ${member.imageCount} saved face image(s) from the recognition database.',
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: Text('Cancel'),
            ),
            FilledButton.icon(
              style: FilledButton.styleFrom(
                backgroundColor: AppColors.danger,
                foregroundColor: Colors.white,
              ),
              onPressed: () => Navigator.of(context).pop(true),
              icon: Icon(Icons.delete_outline),
              label: Text('Delete member'),
            ),
          ],
        );
      },
    );

    if (confirmed != true) {
      return;
    }

    setState(() => _deletingMemberIds.add(member.id));
    try {
      await _memberService.deleteMember(member.id);
      if (!mounted) return;
      _refreshMembers();
      widget.onMembersChanged();
      showAppSnackBar(
        context,
        message: 'Deleted ${member.name}.',
        tone: AppMessageTone.success,
      );
    } catch (error) {
      if (!mounted) return;
      showAppSnackBar(
        context,
        message: friendlyErrorMessage(error),
        tone: toneForError(error),
      );
    } finally {
      if (mounted) {
        setState(() => _deletingMemberIds.remove(member.id));
      }
    }
  }
}

class _MembersToolbar extends StatelessWidget {
  const _MembersToolbar({
    required this.searchController,
    required this.onClearSearch,
  });

  final TextEditingController searchController;
  final VoidCallback? onClearSearch;

  @override
  Widget build(BuildContext context) {
    return TextField(
      controller: searchController,
      decoration: InputDecoration(
        prefixIcon: Icon(Icons.search),
        labelText: context.tr('Search members'),
        suffixIcon: onClearSearch == null
            ? null
            : IconButton(
                onPressed: onClearSearch,
                icon: Icon(Icons.close),
                tooltip: context.tr('Clear search'),
              ),
      ),
    );
  }
}

class _MembersList extends StatelessWidget {
  const _MembersList({
    required this.members,
    required this.deletingMemberIds,
    required this.onDelete,
  });

  final List<MemberModel> members;
  final Set<int> deletingMemberIds;
  final ValueChanged<MemberModel> onDelete;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: members
          .map(
            (member) => Padding(
              padding: const EdgeInsets.only(bottom: AppSpacing.md),
              child: _MemberCard(
                member: member,
                deleting: deletingMemberIds.contains(member.id),
                onDelete: () => onDelete(member),
              ),
            ),
          )
          .toList(),
    );
  }
}

class _MemberCard extends StatelessWidget {
  const _MemberCard({
    required this.member,
    required this.deleting,
    required this.onDelete,
  });

  final MemberModel member;
  final bool deleting;
  final VoidCallback onDelete;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: LayoutBuilder(
          builder: (context, constraints) {
            final identity = Row(
              children: [
                CircleAvatar(
                  radius: 24,
                  backgroundColor: AppColors.tealSoft,
                  foregroundColor: AppColors.teal,
                  child: Text(
                    _initialsFor(member.name),
                    style: TextStyle(fontWeight: FontWeight.w900),
                  ),
                ),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        member.name,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.w900,
                          color: AppColors.text,
                        ),
                      ),
                      const SizedBox(height: AppSpacing.xs),
                      Text(
                        'Registered ${formatBackendTimestamp(member.createdAt)}',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: textTheme.bodySmall?.copyWith(
                          color: AppColors.textMuted,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            );
            final metadata = Wrap(
              spacing: AppSpacing.sm,
              runSpacing: AppSpacing.sm,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                StatusBadge(
                  icon: Icons.image_outlined,
                  label:
                      '${member.imageCount} image${member.imageCount == 1 ? '' : 's'}',
                ),
                StatusBadge(
                  icon: Icons.calendar_today_outlined,
                  label: formatBackendTimestamp(
                    member.createdAt,
                    style: TimestampDisplayStyle.dateOnly,
                    fallback: 'Unknown date',
                  ),
                ),
              ],
            );
            final deleteButton = deleting
                ? const SizedBox.square(
                    dimension: 40,
                    child: Padding(
                      padding: EdgeInsets.all(AppSpacing.sm),
                      child: CircularProgressIndicator(strokeWidth: 2),
                    ),
                  )
                : IconButton(
                    onPressed: onDelete,
                    icon: Icon(Icons.delete_outline),
                    color: AppColors.danger,
                    tooltip: context.tr('Delete member'),
                  );

            if (constraints.maxWidth < AppBreakpoints.compact) {
              return Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  identity,
                  const SizedBox(height: AppSpacing.md),
                  metadata,
                  const SizedBox(height: AppSpacing.sm),
                  Align(alignment: Alignment.centerRight, child: deleteButton),
                ],
              );
            }

            return Row(
              children: [
                Expanded(flex: 5, child: identity),
                const SizedBox(width: AppSpacing.lg),
                Expanded(flex: 4, child: metadata),
                const SizedBox(width: AppSpacing.md),
                deleteButton,
              ],
            );
          },
        ),
      ),
    );
  }

  static String _initialsFor(String name) {
    final parts = name.trim().split(RegExp(r'\s+'));
    if (parts.isEmpty || parts.first.isEmpty) {
      return '?';
    }
    if (parts.length == 1) {
      return parts.first.characters.first.toUpperCase();
    }
    return '${parts.first.characters.first}${parts.last.characters.first}'
        .toUpperCase();
  }
}

class _MembersLoadingState extends StatelessWidget {
  const _MembersLoadingState();

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const SectionHeader(
              title: 'Loading members',
              subtitle: 'Fetching registered people from the backend.',
            ),
            const LinearProgressIndicator(),
            const SizedBox(height: AppSpacing.lg),
            ...List.generate(
              3,
              (index) => Padding(
                padding: EdgeInsets.only(bottom: AppSpacing.md),
                child: _LoadingMemberRow(),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _LoadingMemberRow extends StatelessWidget {
  const _LoadingMemberRow();

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        border: Border.all(color: AppColors.border),
        borderRadius: BorderRadius.circular(AppRadii.sm),
      ),
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.lg),
        child: Row(
          children: [
            CircleAvatar(backgroundColor: AppColors.tealSoft),
            SizedBox(width: AppSpacing.md),
            Expanded(child: LinearProgressIndicator()),
          ],
        ),
      ),
    );
  }
}

class _MembersErrorState extends StatelessWidget {
  const _MembersErrorState({required this.message, required this.onRetry});

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return EmptyPanel(
      icon: Icons.error_outline,
      title: 'Could not load members',
      message: friendlyErrorMessage(message),
      action: FilledButton.icon(
        onPressed: onRetry,
        icon: Icon(Icons.refresh),
        label: Text('Retry'),
      ),
    );
  }
}
