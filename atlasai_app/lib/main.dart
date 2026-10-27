import 'package:flutter/material.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'firebase_options.dart';
import 'theme/app_theme.dart';
import 'screens/auth_gate.dart';
import 'services/fcm_service.dart';

final GlobalKey<ScaffoldMessengerState> rootMessengerKey = GlobalKey<ScaffoldMessengerState>();

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Firebase.initializeApp(
    options: DefaultFirebaseOptions.currentPlatform,
  );

  FirebaseMessaging.onBackgroundMessage(firebaseMessagingBackgroundHandler);

  runApp(const AtlasAIApp());
}

class AtlasAIApp extends StatefulWidget {
  const AtlasAIApp({super.key});

  @override
  State<AtlasAIApp> createState() => _AtlasAIAppState();
}

class _AtlasAIAppState extends State<AtlasAIApp> {
  @override
  void initState() {
    super.initState();
    FcmService().init(rootMessengerKey);
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'WebRAG — Intelligent Website Mining System',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light(),
      darkTheme: AppTheme.dark(),
      themeMode: ThemeMode.system,
      scaffoldMessengerKey: rootMessengerKey,
      home: const AuthGate(),
    );
  }
}
