import 'package:flutter/material.dart';

import 'api_client.dart';

class InvoicesScreen extends StatefulWidget {
  const InvoicesScreen({super.key, required this.apiClient});

  final ApiClient apiClient;

  @override
  State<InvoicesScreen> createState() => _InvoicesScreenState();
}

class _InvoicesScreenState extends State<InvoicesScreen> {
  late Future<List<dynamic>> _future;

  @override
  void initState() {
    super.initState();
    _future = widget.apiClient.fetchInvoices();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Billing')),
      body: FutureBuilder<List<dynamic>>(
        future: _future,
        builder: (context, snapshot) {
          if (snapshot.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snapshot.hasError) {
            return Center(child: Text(ApiClient.errorMessage(snapshot.error!)));
          }
          final invoices = snapshot.data!;
          if (invoices.isEmpty) {
            return const Center(child: Text('No invoices yet.'));
          }
          return ListView.builder(
            padding: const EdgeInsets.all(16),
            itemCount: invoices.length,
            itemBuilder: (context, index) {
              final invoice = invoices[index];
              final balanceDue = double.parse(invoice['balance_due'].toString());
              return Card(
                child: ListTile(
                  title: Text('Invoice #${invoice['id']} — ${invoice['date_issued']}'),
                  subtitle: Text(
                    'You owe \$${invoice['patient_owes']} • '
                    'Paid \$${invoice['amount_paid']}',
                  ),
                  trailing: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    crossAxisAlignment: CrossAxisAlignment.end,
                    children: [
                      Text(
                        '\$${invoice['balance_due']}',
                        style: TextStyle(
                          fontWeight: FontWeight.bold,
                          color: balanceDue > 0 ? Colors.red : Colors.green,
                        ),
                      ),
                      Text(invoice['status'] as String,
                          style: Theme.of(context).textTheme.bodySmall),
                    ],
                  ),
                ),
              );
            },
          );
        },
      ),
    );
  }
}
