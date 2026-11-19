import 'package:flutter/material.dart' hide Text;

import '../theme/app_tokens.dart';
import '../services/member_service.dart';
import '../widgets/localized_text.dart';
import 'members_screen.dart';
import 'register_screen.dart';

enum PeopleSection { registeredPeople, registerPerson }

class PeopleScreen extends StatefulWidget {
  const PeopleScreen({
    super.key,
    required this.refreshToken,
    required this.onMembersChanged,
    this.initialSection = PeopleSection.registeredPeople,
    this.navigationRequest = 0,
    this.memberService = const MemberService(),
    this.imagePicker,
  });

  final int refreshToken;
  final VoidCallback onMembersChanged;
  final PeopleSection initialSection;
  final int navigationRequest;
  final MemberService memberService;
  final RegistrationImagePicker? imagePicker;

  @override
  State<PeopleScreen> createState() => _PeopleScreenState();
}

class _PeopleScreenState extends State<PeopleScreen>
    with SingleTickerProviderStateMixin {
  late final TabController _tabController = TabController(
    length: 2,
    vsync: this,
    initialIndex: widget.initialSection.index,
  );

  @override
  void didUpdateWidget(covariant PeopleScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.navigationRequest != widget.navigationRequest) {
      _tabController.animateTo(widget.initialSection.index);
    }
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return ColoredBox(
      color: AppColors.background,
      child: Column(
        children: [
          Material(
            color: AppColors.surface,
            child: DecoratedBox(
              decoration: BoxDecoration(
                border: Border(bottom: BorderSide(color: AppColors.border)),
              ),
              child: SafeArea(
                bottom: false,
                child: TabBar(
                  controller: _tabController,
                  tabs: const [
                    Tab(
                      icon: Icon(Icons.people_alt_outlined),
                      child: Text('Registered people'),
                    ),
                    Tab(
                      icon: Icon(Icons.person_add_alt_1_outlined),
                      child: Text('Register a person'),
                    ),
                  ],
                ),
              ),
            ),
          ),
          Expanded(
            child: TabBarView(
              controller: _tabController,
              children: [
                MembersScreen(
                  refreshToken: widget.refreshToken,
                  onMembersChanged: widget.onMembersChanged,
                  memberService: widget.memberService,
                ),
                RegisterScreen(
                  refreshToken: widget.refreshToken,
                  onMembersChanged: widget.onMembersChanged,
                  memberService: widget.memberService,
                  imagePicker: widget.imagePicker,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
