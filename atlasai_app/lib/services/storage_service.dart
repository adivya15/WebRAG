import 'dart:convert';
import 'dart:io';
import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:http/http.dart' as http;

/// Day 5: same upload/ingest logic as before — passes technician_id to
/// the backend (enables the person<->equipment graph edges) and
/// persists docType/similarIncidents/alertSent from the response, which
/// the Lessons Learned Timeline screen reads.
///
/// Firebase Storage removed: the project is on the free Spark plan,
/// which doesn't provision a Storage bucket (requires Blaze). The PDF
/// still reaches the backend directly via the /ingest multipart
/// request below — that's what actually drives ingestion, entity
/// extraction, the Knowledge Graph, and Lessons Learned matching.
/// Storage was only ever used for a persistent download link
/// (`storageUrl`), which nothing else in the app reads from — dropping
/// it doesn't remove any real functionality, just that link.
class StorageService {
  final FirebaseFirestore _db = FirebaseFirestore.instance;

  final String backendBaseUrl;

  StorageService({
    this.backendBaseUrl = 'http://10.201.169.154:8000',
  });

  

  Future<Map<String, dynamic>> uploadAndIngest(
    File file,
    String fileName, {
    String? equipmentId,
  }) async {
    final uid = FirebaseAuth.instance.currentUser?.uid ?? 'unknown';

    final docRef = await _db.collection('documents').add({
      'fileName': fileName,
      'uploadedBy': uid,
      'uploadedAt': FieldValue.serverTimestamp(),
      'status': 'pending',
      'linkedEquipmentIds': <String>[],
    });

    try {
      final request = http.MultipartRequest(
        'POST',
        Uri.parse('$backendBaseUrl/ingest'),
      );
      request.files.add(await http.MultipartFile.fromPath('file', file.path));
      if (equipmentId != null) {
        request.fields['equipment_id'] = equipmentId;
      }
      // Day 5: lets the backend build technician<->document and
      // technician<->equipment graph edges.
      request.fields['technician_id'] = uid;

      final streamed = await request.send();
      final res = await http.Response.fromStream(streamed);

      if (res.statusCode != 200) {
        await docRef.update({'status': 'failed'});
        throw Exception('Ingest failed: ${res.statusCode} ${res.body}');
      }

      final result = jsonDecode(res.body) as Map<String, dynamic>;
      final equipmentTags = List<String>.from(result['equipmentTags'] ?? []);
      final graphEdges = List<Map<String, dynamic>>.from(
        (result['graphEdges'] as List).map((e) => Map<String, dynamic>.from(e)),
      );
      // Day 5: additive fields from the updated /ingest response.
      final docType = result['docType'] as String?;
      final similarIncidents = List<Map<String, dynamic>>.from(
        (result['similarIncidents'] as List? ?? []).map((e) => Map<String, dynamic>.from(e)),
      );
      final alertSent = result['alertSent'] as bool? ?? false;

      final batch = _db.batch();
      for (final edge in graphEdges) {
        final edgeRef = _db.collection('graph_edges').doc(edge['edgeId'] as String);
        batch.set(edgeRef, edge);
      }
      batch.update(docRef, {
        'status': 'ingested',
        'linkedEquipmentIds': equipmentTags,
        'backendDocId': result['docId'],
        'docType': docType,
        'similarIncidents': similarIncidents,
        'alertSent': alertSent,
      });
      await batch.commit();

      return result;
    } catch (e) {
      await docRef.update({'status': 'failed'});
      rethrow;
    }
  }
}