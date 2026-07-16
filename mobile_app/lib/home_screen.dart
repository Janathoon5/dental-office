import 'package:flutter/material.dart';

import 'api_client.dart';
import 'appointments_screen.dart';
import 'dashboard_screen.dart';
import 'invoices_screen.dart';
import 'login_screen.dart';
import 'messages_screen.dart';
import 'profile_screen.dart';
import 'push_notifications.dart';
import 'records_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key, required this.apiClient});

  final ApiClient apiClient;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int _tabIndex = 0;

  @override
  void initState() {
    super.initState();
    // Fire-and-forget: a missing/failed token registration shouldn't block
    // using the app, just means this device won't get push notifications.
    registerDeviceToken(widget.apiClient);
  }

  Future<void> _logout() async {
    await widget.apiClient.clearTokens();
    if (!mounted) return;
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute(
        builder: (_) => LoginScreen(apiClient: widget.apiClient),
      ),
      (route) => false,
    );
  }

  @override
  Widget build(BuildContext context) {
    final screens = [
      DashboardScreen(apiClient: widget.apiClient),
      AppointmentsScreen(apiClient: widget.apiClient),
      RecordsScreen(apiClient: widget.apiClient),
      InvoicesScreen(apiClient: widget.apiClient),
      MessagesScreen(apiClient: widget.apiClient),
      ProfileScreen(apiClient: widget.apiClient),
    ];

    return Scaffold(
      body: IndexedStack(index: _tabIndex, children: screens),
      floatingActionButton: _tabIndex == 0
          ? FloatingActionButton.small(
              onPressed: _logout,
              tooltip: 'Log out',
              child: const Icon(Icons.logout),
            )
          : null,
      bottomNavigationBar: NavigationBar(
        selectedIndex: _tabIndex,
        onDestinationSelected: (index) => setState(() => _tabIndex = index),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.home), label: 'Home'),
          NavigationDestination(icon: Icon(Icons.calendar_month), label: 'Visits'),
          NavigationDestination(icon: Icon(Icons.folder_shared), label: 'Records'),
          NavigationDestination(icon: Icon(Icons.receipt_long), label: 'Billing'),
          NavigationDestination(icon: Icon(Icons.chat_bubble_outline), label: 'Messages'),
          NavigationDestination(icon: Icon(Icons.person), label: 'Profile'),
        ],
      ),
    );
  }
}
