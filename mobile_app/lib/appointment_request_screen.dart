import 'package:flutter/material.dart';

import 'api_client.dart';

const _appointmentTypes = {
  'checkup': 'Checkup',
  'cleaning': 'Cleaning',
  'filling': 'Filling',
  'extraction': 'Extraction',
  'consultation': 'Consultation',
  'other': 'Other',
};

class AppointmentRequestScreen extends StatefulWidget {
  const AppointmentRequestScreen({super.key, required this.apiClient, this.existing});

  final ApiClient apiClient;
  final Map<String, dynamic>? existing;

  @override
  State<AppointmentRequestScreen> createState() => _AppointmentRequestScreenState();
}

class _AppointmentRequestScreenState extends State<AppointmentRequestScreen> {
  DateTime? _date;
  TimeOfDay? _time;
  String _appointmentType = 'checkup';
  final _messageController = TextEditingController();
  bool _submitting = false;
  String? _error;

  bool get _editing => widget.existing != null;

  @override
  void initState() {
    super.initState();
    final existing = widget.existing;
    if (existing != null) {
      _date = DateTime.parse(existing['preferred_date'] as String);
      final timeParts = (existing['preferred_time'] as String).split(':');
      _time = TimeOfDay(hour: int.parse(timeParts[0]), minute: int.parse(timeParts[1]));
      _appointmentType = existing['appointment_type'] as String;
      _messageController.text = existing['message'] as String? ?? '';
    }
  }

  @override
  void dispose() {
    _messageController.dispose();
    super.dispose();
  }

  Future<void> _pickDate() async {
    final picked = await showDatePicker(
      context: context,
      initialDate: _date ?? DateTime.now().add(const Duration(days: 1)),
      firstDate: DateTime.now(),
      lastDate: DateTime.now().add(const Duration(days: 365)),
    );
    if (picked != null) setState(() => _date = picked);
  }

  Future<void> _pickTime() async {
    final picked = await showTimePicker(
      context: context,
      initialTime: _time ?? const TimeOfDay(hour: 9, minute: 0),
    );
    if (picked != null) setState(() => _time = picked);
  }

  Future<void> _submit() async {
    if (_date == null || _time == null) {
      setState(() => _error = 'Please choose a date and time.');
      return;
    }
    setState(() {
      _submitting = true;
      _error = null;
    });

    final dateStr =
        '${_date!.year.toString().padLeft(4, '0')}-${_date!.month.toString().padLeft(2, '0')}-${_date!.day.toString().padLeft(2, '0')}';
    final timeStr = '${_time!.hour.toString().padLeft(2, '0')}:${_time!.minute.toString().padLeft(2, '0')}:00';

    final fields = {
      'preferred_date': dateStr,
      'preferred_time': timeStr,
      'appointment_type': _appointmentType,
      'message': _messageController.text,
    };

    try {
      if (_editing) {
        await widget.apiClient.updateAppointmentRequest(widget.existing!['id'] as int, fields);
      } else {
        await widget.apiClient.createAppointmentRequest(fields);
      }
      if (!mounted) return;
      Navigator.of(context).pop(true);
    } catch (e) {
      setState(() => _error = ApiClient.errorMessage(e));
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(_editing ? 'Edit Request' : 'Request Appointment')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: ListView(
          children: [
            ListTile(
              title: Text(_date == null ? 'Choose a date' : _date!.toString().split(' ').first),
              trailing: const Icon(Icons.calendar_today),
              onTap: _pickDate,
            ),
            ListTile(
              title: Text(_time == null ? 'Choose a time' : _time!.format(context)),
              trailing: const Icon(Icons.access_time),
              onTap: _pickTime,
            ),
            const SizedBox(height: 8),
            DropdownButtonFormField<String>(
              initialValue: _appointmentType,
              decoration: const InputDecoration(labelText: 'Appointment type'),
              items: [
                for (final entry in _appointmentTypes.entries)
                  DropdownMenuItem(value: entry.key, child: Text(entry.value)),
              ],
              onChanged: (value) => setState(() => _appointmentType = value!),
            ),
            const SizedBox(height: 16),
            TextField(
              controller: _messageController,
              decoration: const InputDecoration(labelText: 'Additional notes (optional)'),
              maxLines: 3,
            ),
            const SizedBox(height: 24),
            if (_error != null)
              Padding(
                padding: const EdgeInsets.only(bottom: 16),
                child: Text(_error!, style: const TextStyle(color: Colors.red)),
              ),
            ElevatedButton(
              onPressed: _submitting ? null : _submit,
              child: _submitting
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : Text(_editing ? 'Save Changes' : 'Submit Request'),
            ),
          ],
        ),
      ),
    );
  }
}
