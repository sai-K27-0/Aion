import 'package:freezed_annotation/freezed_annotation.dart';
import 'package:isar/isar.dart';

part 'block_model.freezed.dart';
part 'block_model.g.dart';

@freezed
@Collection(ignore: {'copyWith'})
class BlockModel with _$BlockModel {
  const BlockModel._();

  const factory BlockModel({
    @Id() required int id, // Local Isar ID
    @Index(unique: true) required String uuid,
    required String type,
    Map<String, dynamic>? properties,
    @Default([]) List<String> content,
    @Index() String? parentUuid,
    @Default(0) int order,
    @Default(false) bool isSynced,
    DateTime? createdAt,
    DateTime? updatedAt,
  }) = _BlockModel;

  factory BlockModel.fromJson(Map<String, dynamic> json) => 
      _$BlockModelFromJson(json);
}
