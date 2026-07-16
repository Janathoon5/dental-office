import 'dart:io';

import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';

import 'api_client.dart';

final _localNotifications = FlutterLocalNotificationsPlugin();

/// Must be a top-level function — the OS invokes this in a separate,
/// freshly-spawned isolate (with no prior initialization) when a data-only
/// message arrives while the app is backgrounded or fully terminated, hence
/// re-calling Firebase.initializeApp() here. Otherwise there's nothing to
/// do: data-only payloads never auto-display, and the patient will see the
/// real message next time they open the app (the foreground handler below
/// covers the app-already-open case).
@pragma('vm:entry-point')
Future<void> firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  await Firebase.initializeApp();
}

/// Sets up local-notification display for data-only FCM payloads (which,
/// by design, carry no PHI — see messaging/push.py on the Django side) and
/// requests notification permission. Call once at app startup.
Future<void> initPushNotifications() async {
  const androidInit = AndroidInitializationSettings('@mipmap/ic_launcher');
  await _localNotifications.initialize(
    const InitializationSettings(android: androidInit),
  );

  FirebaseMessaging.onBackgroundMessage(firebaseMessagingBackgroundHandler);

  await FirebaseMessaging.instance.requestPermission();

  FirebaseMessaging.onMessage.listen((message) {
    final title = message.data['title'] ?? 'New message';
    final body = message.data['body'] ?? 'You have a new message from your dental office.';
    _localNotifications.show(
      message.hashCode,
      title,
      body,
      const NotificationDetails(
        android: AndroidNotificationDetails(
          'messages',
          'Messages',
          importance: Importance.high,
          priority: Priority.high,
        ),
      ),
    );
  });
}

/// Registers this device's current FCM token with the backend — call after
/// a session is confirmed active (HomeScreen), not at cold start, since the
/// endpoint requires patient auth.
Future<void> registerDeviceToken(ApiClient apiClient) async {
  final token = await FirebaseMessaging.instance.getToken();
  if (token == null) return;
  final platform = Platform.isIOS ? 'ios' : 'android';
  await apiClient.registerDevice(token, platform);
}
