import 'dart:io';
import 'dart:typed_data';

import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart' show rootBundle;
import 'package:safe_device/safe_device.dart';
import 'package:screen_protector/screen_protector.dart';

import 'api_client.dart';
import 'app_lock.dart';
import 'home_screen.dart';
import 'login_screen.dart';
import 'push_notifications.dart';

final navigatorKey = GlobalKey<NavigatorState>();

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // Android picks up config from android/app/google-services.json
  // automatically via the Google Services Gradle plugin — no explicit
  // options needed here. iOS isn't configured yet (no GoogleService-Info
  // .plist — this machine can't build/test iOS at all, see memory).
  await Firebase.initializeApp();
  await initPushNotifications();

  // Blocks screenshots/screen recording and (Android) the recents-list
  // thumbnail; adds an automatic blur-on-background overlay on iOS.
  await ScreenProtector.preventScreenshotOn();
  if (Platform.isIOS) {
    await ScreenProtector.protectDataLeakageWithBlur();
  }

  // Deliberately not also checking SafeDevice.isRealDevice here — running on
  // an emulator isn't itself a compromise, just a dev/testing environment
  // (and is in fact how this app's own testing happens).
  final isJailbroken = await SafeDevice.isJailBroken;
  final caCertBytes = (await rootBundle.load('assets/isrg_root_x1.pem')).buffer.asUint8List();

  runApp(DentalOfficeApp(pinnedCaCertBytes: caCertBytes, isJailbroken: isJailbroken));
}

class DentalOfficeApp extends StatefulWidget {
  const DentalOfficeApp({
    super.key,
    required this.pinnedCaCertBytes,
    required this.isJailbroken,
  });

  final Uint8List pinnedCaCertBytes;
  final bool isJailbroken;

  @override
  State<DentalOfficeApp> createState() => _DentalOfficeAppState();
}

class _DentalOfficeAppState extends State<DentalOfficeApp> {
  late final ApiClient apiClient = ApiClient(
    pinnedCaCertBytes: widget.pinnedCaCertBytes,
    onSessionExpired: _onSessionExpired,
  );

  void _onSessionExpired() {
    navigatorKey.currentState?.pushAndRemoveUntil(
      MaterialPageRoute(builder: (_) => LoginScreen(apiClient: apiClient)),
      (route) => false,
    );
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      navigatorKey: navigatorKey,
      title: 'Dental Office',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(colorScheme: ColorScheme.fromSeed(seedColor: Colors.teal)),
      builder: (context, child) {
        // A compromised OS undermines every other protection in this app,
        // so this is a hard block, not a warning.
        if (widget.isJailbroken) {
          return const _BlockedScreen();
        }
        return AppLock(isSessionActive: apiClient.hasStoredSession, child: child!);
      },
      home: FutureBuilder<bool>(
        future: apiClient.hasStoredSession(),
        builder: (context, snapshot) {
          if (snapshot.connectionState != ConnectionState.done) {
            return const Scaffold(body: Center(child: CircularProgressIndicator()));
          }
          if (snapshot.data == true) {
            return HomeScreen(apiClient: apiClient);
          }
          return LoginScreen(apiClient: apiClient);
        },
      ),
    );
  }
}

class _BlockedScreen extends StatelessWidget {
  const _BlockedScreen();

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                const Icon(Icons.gpp_bad, size: 64, color: Colors.red),
                const SizedBox(height: 16),
                Text(
                  "This app can't run on a rooted or jailbroken device, "
                  "since it stores sensitive medical information that "
                  "depends on your device's built-in security protections.",
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.titleMedium,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
