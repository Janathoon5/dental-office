import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart' show PlatformException;
import 'package:local_auth/local_auth.dart';

// Thrown by local_auth when there's no usable authentication method
// configured at all (no biometrics enrolled and no device PIN/pattern/
// password set) — distinct from the device not supporting auth hardware in
// the first place, which _localAuth.isDeviceSupported() already checks for.
const _noCredentialsConfiguredCodes = {'NotAvailable', 'NotEnrolled'};

/// Wraps the whole app (via MaterialApp.builder, so it persists across
/// screen navigation) to provide two Phase 3 protections in one place:
///  1. A blur overlay whenever the app isn't in the foreground — mitigates
///     the OS app-switcher preview showing PHI in a screenshot-like thumbnail.
///  2. A biometric (or device passcode) re-auth gate on resume, but only
///     when there's an actual logged-in session worth protecting — the
///     login screen itself has nothing to gate.
class AppLock extends StatefulWidget {
  const AppLock({super.key, required this.child, required this.isSessionActive});

  final Widget child;
  final Future<bool> Function() isSessionActive;

  @override
  State<AppLock> createState() => _AppLockState();
}

class _AppLockState extends State<AppLock> with WidgetsBindingObserver {
  final _localAuth = LocalAuthentication();
  bool _locked = false;
  bool _obscured = false;
  bool _authenticating = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _maybeLockOnStart();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  Future<void> _maybeLockOnStart() async {
    if (await widget.isSessionActive()) {
      setState(() => _locked = true);
      _attemptUnlock();
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) async {
    if (state == AppLifecycleState.resumed) {
      setState(() => _obscured = false);
      if (_locked) _attemptUnlock();
      return;
    }
    setState(() => _obscured = true);
    if (await widget.isSessionActive()) {
      setState(() => _locked = true);
    }
  }

  Future<void> _attemptUnlock() async {
    if (_authenticating) return;
    _authenticating = true;
    try {
      final canAuthenticate =
          await _localAuth.isDeviceSupported() || await _localAuth.canCheckBiometrics;
      if (!canAuthenticate) {
        // No device authentication configured at all — a device capability
        // gap, not a security decision we're making, so don't lock a
        // legitimate patient out of their own appointments over it.
        setState(() => _locked = false);
        return;
      }
      final didAuthenticate = await _localAuth.authenticate(
        localizedReason: 'Unlock to access your dental records',
        options: const AuthenticationOptions(biometricOnly: false, stickyAuth: true),
      );
      if (didAuthenticate) {
        setState(() => _locked = false);
      }
    } on PlatformException catch (e) {
      if (_noCredentialsConfiguredCodes.contains(e.code)) {
        // isDeviceSupported()/canCheckBiometrics only check for capable
        // hardware — they don't catch "supported but nothing is actually
        // enrolled" (no fingerprint, no PIN/pattern/password set), which
        // only surfaces once authenticate() itself is attempted. Without
        // this, a patient on a device with no lock screen configured would
        // be locked out with no way back in — the Unlock button would just
        // keep hitting this same error forever.
        setState(() => _locked = false);
      }
      // Any other PlatformException (e.g. the user cancelled the prompt):
      // leave locked; the Unlock button lets them retry.
    } finally {
      _authenticating = false;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        widget.child,
        if (_obscured)
          Positioned.fill(
            child: BackdropFilter(
              filter: ImageFilter.blur(sigmaX: 24, sigmaY: 24),
              child: Container(color: Colors.black.withValues(alpha: 0.6)),
            ),
          ),
        if (_locked)
          Positioned.fill(
            child: Material(
              color: Theme.of(context).scaffoldBackgroundColor,
              child: Center(
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    const Icon(Icons.lock_outline, size: 64),
                    const SizedBox(height: 16),
                    const Text('App locked'),
                    const SizedBox(height: 24),
                    ElevatedButton(
                      onPressed: _attemptUnlock,
                      child: const Text('Unlock'),
                    ),
                  ],
                ),
              ),
            ),
          ),
      ],
    );
  }
}
