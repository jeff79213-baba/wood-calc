/// Flutter 分割結果互動範例
/// 功能：顯示照片 + 區塊遮罩疊加層 + 點選區塊選素材

import 'dart:ui' as ui;
import 'dart:io';
import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

class SegmentationView extends StatelessWidget {
  final String imagePath;
  final List<Map<String, dynamic>> segments;
  final double imageWidth;
  final double imageHeight;

  const SegmentationView({
    super.key,
    required this.imagePath,
    required this.segments,
    required this.imageWidth,
    required this.imageHeight,
  });

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final maxW = constraints.maxWidth;
        final scale = maxW / imageWidth;

        return Stack(
          children: [
            // 原始照片
            Image.file(File(imagePath), fit: BoxFit.fitWidth),

            // 遮罩疊加 (可點選)
            ...segments.map((seg) => Positioned.fill(
                  child: GestureDetector(
                    onTap: () => _onSegmentTap(context, seg),
                    child: CustomPaint(
                      painter: SegmentPainter(
                        polygon: seg['polygon'] as List,
                        scale: scale,
                        color: _colorForLabel(seg['label'] as String),
                      ),
                    ),
                  ),
                )),
          ],
        );
      },
    );
  }

  void _onSegmentTap(BuildContext context, Map<String, dynamic> segment) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('已點選區塊: ${segment['label']} '
            '(信心度: ${(segment['confidence'] as double).toStringAsFixed(2)})'),
        action: SnackBarAction(
          label: '選擇材質',
          onPressed: () {
            // 導向素材選擇頁面
          },
        ),
      ),
    );
  }

  Color _colorForLabel(String label) {
    final colors = [
      Colors.blue.withValues(alpha: 0.7),
      Colors.red.withValues(alpha: 0.7),
      Colors.green.withValues(alpha: 0.7),
      Colors.orange.withValues(alpha: 0.7),
      Colors.purple.withValues(alpha: 0.7),
      Colors.teal.withValues(alpha: 0.7),
    ];
    final hash = label.hashCode;
    return colors[hash.abs() % colors.length];
  }
}

class SegmentPainter extends CustomPainter {
  final List polygon;
  final double scale;
  final Color color;

  SegmentPainter({
    required this.polygon,
    required this.scale,
    required this.color,
  });

  @override
  void paint(Canvas canvas, Size size) {
    if (polygon.isEmpty) return;

    final paint = Paint()
      ..color = color
      ..style = PaintingStyle.fill;

    final strokePaint = Paint()
      ..color = Colors.white
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2.0;

    final path = Path();
    final points = polygon.map((pt) {
      final list = pt as List;
      return Offset(
        (list[0] as num).toDouble() * scale,
        (list[1] as num).toDouble() * scale,
      );
    }).toList();

    if (points.isEmpty) return;

    path.moveTo(points[0].dx, points[0].dy);
    for (int i = 1; i < points.length; i++) {
      path.lineTo(points[i].dx, points[i].dy);
    }
    path.close();

    canvas.drawPath(path, paint);
    canvas.drawPath(path, strokePaint);
  }

  @override
  bool shouldRepaint(covariant SegmentPainter oldDelegate) =>
      oldDelegate.polygon != polygon || oldDelegate.color != color;
}
