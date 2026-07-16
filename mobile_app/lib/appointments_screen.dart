import 'package:flutter/material.dart';

import 'api_client.dart';
import 'appointment_request_screen.dart';

class AppointmentsScreen extends StatefulWidget {
  const AppointmentsScreen({super.key, required this.apiClient});

  final ApiClient apiClient;

  @override
  State<AppointmentsScreen> createState() => _AppointmentsScreenState();
}

class _AppointmentsScreenState extends State<AppointmentsScreen> {
  late Future<_AppointmentsData> _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<_AppointmentsData> _load() async {
    final upcoming = await widget.apiClient.fetchAppointments(scope: 'upcoming');
    final past = await widget.apiClient.fetchAppointments(scope: 'past');
    final pendingRequests = await widget.apiClient.fetchAppointmentRequests();
    return _AppointmentsData(upcoming: upcoming, past: past, pendingRequests: pendingRequests);
  }

  void _refresh() => setState(() {
        _future = _load();
      });

  Future<void> _openRequestForm({Map<String, dynamic>? existing}) async {
    final changed = await Navigator.of(context).push<bool>(
      MaterialPageRoute(
        builder: (_) => AppointmentRequestScreen(
          apiClient: widget.apiClient,
          existing: existing,
        ),
      ),
    );
    if (changed == true) _refresh();
  }

  Future<void> _cancelRequest(int id) async {
    await widget.apiClient.cancelAppointmentRequest(id);
    _refresh();
  }

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 2,
      child: Scaffold(
        appBar: AppBar(
          title: const Text('Appointments'),
          bottom: const TabBar(tabs: [Tab(text: 'Upcoming'), Tab(text: 'Past')]),
        ),
        floatingActionButton: FloatingActionButton(
          onPressed: () => _openRequestForm(),
          tooltip: 'Request an appointment',
          child: const Icon(Icons.add),
        ),
        body: FutureBuilder<_AppointmentsData>(
          future: _future,
          builder: (context, snapshot) {
            if (snapshot.connectionState != ConnectionState.done) {
              return const Center(child: CircularProgressIndicator());
            }
            if (snapshot.hasError) {
              return Center(child: Text(ApiClient.errorMessage(snapshot.error!)));
            }
            final data = snapshot.data!;
            return TabBarView(
              children: [
                _UpcomingTab(
                  appointments: data.upcoming,
                  pendingRequests: data.pendingRequests,
                  onEditRequest: (r) => _openRequestForm(existing: r),
                  onCancelRequest: (id) => _cancelRequest(id),
                ),
                _PastTab(appointments: data.past),
              ],
            );
          },
        ),
      ),
    );
  }
}

class _AppointmentsData {
  _AppointmentsData({required this.upcoming, required this.past, required this.pendingRequests});
  final List<dynamic> upcoming;
  final List<dynamic> past;
  final List<dynamic> pendingRequests;
}

class _UpcomingTab extends StatelessWidget {
  const _UpcomingTab({
    required this.appointments,
    required this.pendingRequests,
    required this.onEditRequest,
    required this.onCancelRequest,
  });

  final List<dynamic> appointments;
  final List<dynamic> pendingRequests;
  final void Function(Map<String, dynamic>) onEditRequest;
  final void Function(int) onCancelRequest;

  @override
  Widget build(BuildContext context) {
    if (appointments.isEmpty && pendingRequests.isEmpty) {
      return const Center(child: Text('No upcoming appointments.'));
    }
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        if (appointments.isNotEmpty) ...[
          Text('Confirmed', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          for (final appt in appointments)
            Card(
              child: ListTile(
                title: Text('${appt['date']} at ${appt['start_time']}'),
                subtitle: Text(
                  '${appt['appointment_type']} with ${appt['dentist_name'] ?? 'TBD'}',
                ),
              ),
            ),
          const SizedBox(height: 24),
        ],
        if (pendingRequests.isNotEmpty) ...[
          Text('Pending requests', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          for (final r in pendingRequests)
            Card(
              child: ListTile(
                title: Text('${r['preferred_date']} at ${r['preferred_time']}'),
                subtitle: Text(r['appointment_type']),
                trailing: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    IconButton(
                      icon: const Icon(Icons.edit),
                      onPressed: () => onEditRequest(r as Map<String, dynamic>),
                    ),
                    IconButton(
                      icon: const Icon(Icons.cancel),
                      onPressed: () => onCancelRequest(r['id'] as int),
                    ),
                  ],
                ),
              ),
            ),
        ],
      ],
    );
  }
}

class _PastTab extends StatelessWidget {
  const _PastTab({required this.appointments});

  final List<dynamic> appointments;

  @override
  Widget build(BuildContext context) {
    if (appointments.isEmpty) {
      return const Center(child: Text('No past appointments.'));
    }
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        for (final appt in appointments)
          Card(
            child: ListTile(
              title: Text('${appt['date']} at ${appt['start_time']}'),
              subtitle: Text('${appt['appointment_type']} — ${appt['status']}'),
            ),
          ),
      ],
    );
  }
}
