/// 建材即時模擬替換 App — Flutter API 整合範例
/// 使用方式: flutter pub add dio

import 'dart:io';
import 'dart:convert';
import 'package:dio/dio.dart';

class MaterialSwapApi {
  final Dio _dio;

  MaterialSwapApi(String baseUrl)
      : _dio = Dio(BaseOptions(
          baseUrl: baseUrl,
          connectTimeout: const Duration(seconds: 30),
          receiveTimeout: const Duration(seconds: 120),
        ));

  /// 1. 上傳素材照片
  Future<Map<String, dynamic>> uploadMaterial({
    required File imageFile,
    required String name,
    String category = 'tile',
  }) async {
    final formData = FormData.fromMap({
      'file': await MultipartFile.fromFile(imageFile.path,
          filename: imageFile.path.split('/').last),
      'name': name,
      'category': category,
    });
    final res = await _dio.post('/api/materials/upload', data: formData);
    return res.data;
  }

  /// 2. 取得素材庫列表
  Future<List<Map<String, dynamic>>> listMaterials({
    String? category,
  }) async {
    final res = await _dio.get('/api/materials', queryParameters: {
      if (category != null) 'category': category,
    });
    return List<Map<String, dynamic>>.from(res.data);
  }

  /// 3. 上傳空間照片並執行 AI 分割
  Future<Map<String, dynamic>> uploadRoom({
    required File imageFile,
    String name = '未命名專案',
    String? roomType,
  }) async {
    final formData = FormData.fromMap({
      'file': await MultipartFile.fromFile(imageFile.path,
          filename: imageFile.path.split('/').last),
      'name': name,
      if (roomType != null) 'room_type': roomType,
    });
    final res = await _dio.post('/api/spatial/upload', data: formData);
    return res.data;
  }

  /// 4. 取得分割區塊列表
  Future<List<Map<String, dynamic>>> getSegments(String projectId) async {
    final res = await _dio.get('/api/spatial/$projectId/segments');
    return List<Map<String, dynamic>>.from(res.data);
  }

  /// 5. 替換單一區塊紋理
  Future<Map<String, dynamic>> replaceSegment({
    required String projectId,
    required String segmentId,
    required String materialId,
    String blendMode = 'multiply',
  }) async {
    final res = await _dio.post('/api/spatial/$projectId/replace', data: {
      'segment_id': segmentId,
      'material_id': materialId,
      'blend_mode': blendMode,
    });
    return res.data;
  }

  /// 6. 批次替換多個區塊
  Future<Map<String, dynamic>> batchReplace({
    required String projectId,
    required List<Map<String, String>> replacements,
  }) async {
    final res = await _dio.post('/api/spatial/$projectId/replace-batch', data: {
      'replacements': replacements,
    });
    return res.data;
  }

  /// 7. 健康檢查
  Future<bool> healthCheck() async {
    try {
      final res = await _dio.get('/api/health');
      return res.data['status'] == 'ok';
    } catch (_) {
      return false;
    }
  }
}
