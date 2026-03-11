# Suppress Play Core missing class warnings (Flutter engine references
# deferred components API but Aion doesn't use it)
-dontwarn com.google.android.play.core.**

# Flutter specific rules
-keep class io.flutter.app.** { *; }
-keep class io.flutter.plugin.** { *; }
-keep class io.flutter.util.** { *; }
-keep class io.flutter.view.** { *; }
-keep class io.flutter.** { *; }
-keep class io.flutter.plugins.** { *; }

# Keep Isar database
-keep class dev.isar.** { *; }
-keep class **.isar.** { *; }

# Keep JSON serialization
-keepattributes *Annotation*
-keepattributes Signature
-keep class * extends com.google.gson.TypeAdapter
-keep class * implements com.google.gson.TypeAdapterFactory
-keep class * implements com.google.gson.JsonSerializer
-keep class * implements com.google.gson.JsonDeserializer

# Keep model classes
-keep class com.aion.mobile.models.** { *; }
