import 'dart:convert';
import 'package:isar/isar.dart';

part 'block_model.g.dart';

@collection
class BlockModel {
  Id id = Isar.autoIncrement;

  @Index(unique: true)
  late String uuid;

  late String type;

  /// Properties stored as JSON string (Isar doesn't support Map)
  String? propertiesJson;

  List<String> content = [];

  @Index()
  String? parentUuid;

  int order = 0;

  bool isSynced = false;

  DateTime? createdAt;
  DateTime? updatedAt;

  // ── Convenience accessors for properties map ──

  @ignore
  Map<String, dynamic>? get properties {
    if (propertiesJson == null) return null;
    try {
      return jsonDecode(propertiesJson!) as Map<String, dynamic>;
    } catch (_) {
      return null;
    }
  }

  set properties(Map<String, dynamic>? value) {
    propertiesJson = value != null ? jsonEncode(value) : null;
  }

  // ── Manual copyWith ──

  BlockModel copyWith({
    Id? id,
    String? uuid,
    String? type,
    Map<String, dynamic>? properties,
    List<String>? content,
    String? parentUuid,
    int? order,
    bool? isSynced,
    DateTime? createdAt,
    DateTime? updatedAt,
  }) {
    final copy = BlockModel()
      ..id = id ?? this.id
      ..uuid = uuid ?? this.uuid
      ..type = type ?? this.type
      ..propertiesJson = properties != null
          ? jsonEncode(properties)
          : propertiesJson
      ..content = content ?? List<String>.from(this.content)
      ..parentUuid = parentUuid ?? this.parentUuid
      ..order = order ?? this.order
      ..isSynced = isSynced ?? this.isSynced
      ..createdAt = createdAt ?? this.createdAt
      ..updatedAt = updatedAt ?? this.updatedAt;
    return copy;
  }

  // ── JSON serialization for API ──

  factory BlockModel.fromJson(Map<String, dynamic> json) {
    return BlockModel()
      ..id = json['id'] is int ? json['id'] as int : Isar.autoIncrement
      ..uuid = json['uuid'] as String
      ..type = json['type'] as String? ?? 'default'
      ..propertiesJson = json['properties'] != null
          ? jsonEncode(json['properties'])
          : null
      ..content = (json['content'] as List<dynamic>?)
              ?.map((e) => e.toString())
              .toList() ??
          []
      ..parentUuid = json['parentUuid'] as String?
      ..order = json['order'] as int? ?? 0
      ..isSynced = json['isSynced'] as bool? ?? false
      ..createdAt = json['createdAt'] != null
          ? DateTime.parse(json['createdAt'] as String)
          : null
      ..updatedAt = json['updatedAt'] != null
          ? DateTime.parse(json['updatedAt'] as String)
          : null;
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'uuid': uuid,
        'type': type,
        'properties': properties,
        'content': content,
        'parentUuid': parentUuid,
        'order': order,
        'isSynced': isSynced,
        'createdAt': createdAt?.toIso8601String(),
        'updatedAt': updatedAt?.toIso8601String(),
      };
}
