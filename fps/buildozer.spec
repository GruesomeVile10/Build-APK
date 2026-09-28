[app]

# (str) Title of your application
title = BGMI Performance Monitor

# (str) Package name
package.name = bgmimonitor

# (str) Package domain (needed for android/ios packaging)
package.domain = org.bgmitools

# (str) Source code where the main.py live
source.dir = .

# (list) Source files to include (let empty to include all the files)
source.include_exts = py,png,jpg,kv,atlas,json

# (str) Application versioning
version = 1.0

# (list) Application requirements
# psutil / plyer / pyjnius are optional but recommended for full feature support
requirements = python3,kivy,psutil,plyer,pyjnius

# (str) Supported orientation (one of landscape, sensorLandscape, portrait or all)
orientation = portrait

# (bool) Indicate if the application should be fullscreen or not
fullscreen = 0

# (list) Permissions
android.permissions = INTERNET,ACCESS_NETWORK_STATE,SYSTEM_ALERT_WINDOW,WAKE_LOCK,FOREGROUND_SERVICE

# (int) Target Android API, should be as high as possible.
android.api = 33

# (int) Minimum API your APK will support.
android.minapi = 21

# (str) Android NDK version to use
android.ndk = 25b

# (list) The Android archs to build for
android.archs = arm64-v8a, armeabi-v7a

# (bool) enables Android auto backup feature (Android API >=23)
android.allow_backup = True

# (str) Android NDK API level
android.ndk_api = 27

# (list) Gradle dependencies
android.gradle_dependencies = 

# (bool) Skip building libpython if already present
android.skip_libpython = False

# (str) Extra CFLAGS for building extensions
android.cflags = -I/data/data/com.termux/files/usr/include

# (str) Extra LDFLAGS for building extensions
android.ldflags = -L/data/data/com.termux/files/usr/lib

# (str) The entry point (activity) - default is fine for Kivy apps
android.entrypoint = org.kivy.android.PythonActivity

# (str) Presplash / icon - add your own png files here if you have them
#icon.filename = %(source.dir)s/icon.png
#presplash.filename = %(source.dir)s/presplash.png

[buildozer]

# (int) Log level (0 = error only, 1 = info, 2 = debug (with command output))
log_level = 2

# (int) Display warning if buildozer is run as root
warn_on_root = 1
