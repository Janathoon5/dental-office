import 'package:flutter/material.dart';

import 'api_client.dart';

class RecordsScreen extends StatefulWidget {
  const RecordsScreen({super.key, required this.apiClient});

  final ApiClient apiClient;

  @override
  State<RecordsScreen> createState() => _RecordsScreenState();
}

class _RecordsScreenState extends State<RecordsScreen> {
  late Future<_RecordsData> _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<_RecordsData> _load() async {
    final records = await widget.apiClient.fetchTreatmentRecords();
    final plans = await widget.apiClient.fetchTreatmentPlans();
    return _RecordsData(records: records, plans: plans);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Records')),
      body: FutureBuilder<_RecordsData>(
        future: _future,
        builder: (context, snapshot) {
          if (snapshot.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snapshot.hasError) {
            return Center(child: Text(ApiClient.errorMessage(snapshot.error!)));
          }
          final data = snapshot.data!;
          if (data.records.isEmpty && data.plans.isEmpty) {
            return const Center(child: Text('No records yet.'));
          }
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              if (data.plans.isNotEmpty) ...[
                Text('Treatment plans', style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: 8),
                for (final plan in data.plans)
                  Card(
                    child: ExpansionTile(
                      title: Text(plan['title'] as String),
                      subtitle: Text('${plan['status']} — total \$${plan['total_cost']}'),
                      children: [
                        for (final item in (plan['items'] as List<dynamic>))
                          ListTile(
                            title: Text(item['procedure'] as String),
                            subtitle: item['tooth_number'] == ''
                                ? null
                                : Text('Tooth ${item['tooth_number']}'),
                            trailing: Text('\$${item['estimated_cost']}'),
                          ),
                      ],
                    ),
                  ),
                const SizedBox(height: 24),
              ],
              if (data.records.isNotEmpty) ...[
                Text('Treatment history', style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: 8),
                for (final record in data.records)
                  Card(
                    child: ListTile(
                      title: Text(record['procedure'] as String),
                      subtitle: Text(
                        '${record['date']}'
                        '${record['tooth_number'] == '' ? '' : ' — tooth ${record['tooth_number']}'}'
                        '${record['dentist_name'] == '' ? '' : ' — Dr. ${record['dentist_name']}'}',
                      ),
                    ),
                  ),
              ],
            ],
          );
        },
      ),
    );
  }
}

class _RecordsData {
  _RecordsData({required this.records, required this.plans});
  final List<dynamic> records;
  final List<dynamic> plans;
}
