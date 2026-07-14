import 'package:flutter/material.dart';

import 'api_client.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key, required this.apiClient});

  final ApiClient apiClient;

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  late Future<Map<String, dynamic>> _dashboardFuture;

  @override
  void initState() {
    super.initState();
    _dashboardFuture = widget.apiClient.fetchDashboard();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Dashboard')),
      body: FutureBuilder<Map<String, dynamic>>(
        future: _dashboardFuture,
        builder: (context, snapshot) {
          if (snapshot.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snapshot.hasError) {
            return Center(
              child: Text('Failed to load dashboard: ${snapshot.error}'),
            );
          }
          final data = snapshot.data!;
          final nextAppointment =
              data['next_appointment'] as Map<String, dynamic>?;
          return Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Welcome, ${data['first_name']}',
                  style: Theme.of(context).textTheme.headlineSmall,
                ),
                const SizedBox(height: 24),
                Text(
                  'Next appointment',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                const SizedBox(height: 8),
                Text(
                  nextAppointment == null
                      ? 'No upcoming appointment scheduled.'
                      : '${nextAppointment['date']} at ${nextAppointment['start_time']} '
                          'with ${nextAppointment['dentist_name']}',
                ),
                const SizedBox(height: 24),
                Text(
                  'Total balance',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                const SizedBox(height: 8),
                Text('\$${data['total_balance']}'),
              ],
            ),
          );
        },
      ),
    );
  }
}
