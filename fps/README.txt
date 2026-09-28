========================================================
 BGMI PERFORMANCE MONITOR - README
========================================================

FILES INCLUDED
--------------
 main.py                    -> The complete app (single file, Kivy).
 buildozer.spec              -> Android build configuration for Buildozer.
 Build_APK_On_Colab.ipynb    -> Ready-made Google Colab notebook that
                                compiles main.py into an .apk in the cloud.
 build_apk.bat               -> Windows helper: zips your files and opens
                                Colab + the notebook for you.

FEATURES
--------
 - Floating, draggable FPS counter (overlay inside the app, works on
   Desktop and Android; a button on the Dashboard can also request the
   Android "draw over other apps" permission for future true system
   overlay support).
 - Live CPU / RAM / Battery / Temperature monitoring (uses psutil on
   desktop, and /proc + battery APIs as a fallback on Android so it
   still works if psutil isn't available).
 - Network Ping + Jitter graph (TCP-based latency measurement, works
   without needing shell/ping binary permissions on modern Android).
 - Session History: press "Start Session" / "Stop Session" on the
   Dashboard to record and save average FPS/CPU/RAM/Ping stats.
 - Device Benchmark: CPU + RAM + rendering test producing an overall
   score, a performance tier (Entry-Level / Mid-Range / High-End /
   Flagship) and a personalized BGMI settings recommendation.
 - Game-specific Profiles: 6 built-in BGMI profiles (Battery Saver,
   Balanced, Performance, Extreme Performance, HD Visuals, HDR Ultra)
   that can be applied/marked active.

--------------------------------------------------------
1) TEST IT ON YOUR PC FIRST (recommended)
--------------------------------------------------------
   pip install kivy psutil plyer
   python main.py

   A window will open showing the live app. Try the Dashboard,
   Network, Benchmark, Profiles and History tabs at the bottom.

--------------------------------------------------------
2) TURN IT INTO AN ANDROID APK - NO WSL NEEDED
--------------------------------------------------------
Buildozer (the tool that packages Kivy apps into APKs) officially
only runs on Linux/macOS. To avoid requiring WSL or a Linux VM on
your Windows PC, use one of these two "pure Python, cloud/on-device"
options:

  OPTION A - Google Colab (recommended, easiest)
  ------------------------------------------------
   1. Double-click "build_apk.bat".
      It will zip main.py + buildozer.spec and open Google Colab
      plus the included notebook file in your browser.
   2. In Colab: File > Upload notebook > choose
      "Build_APK_On_Colab.ipynb".
   3. Run every cell top-to-bottom (Shift+Enter). When asked,
      upload main.py and buildozer.spec.
   4. Wait for the build (~15-25 min the first time). The final
      cell automatically downloads the finished .apk to your PC.
   This entire process is just Python running in Google's cloud -
   nothing is installed on your Windows machine.

  OPTION B - Termux (build directly on your Android phone)
  ------------------------------------------------
   1. Install "Termux" from F-Droid (not the outdated Play Store one).
   2. Copy main.py and buildozer.spec onto your phone.
   3. In Termux:
        pkg update && pkg upgrade
        pkg install python git openjdk-17 -y
        pip install buildozer cython
        cd /path/to/your/project
        buildozer android debug
   4. The finished APK appears inside the "bin" folder.

--------------------------------------------------------
3) INSTALLING THE APK
--------------------------------------------------------
   Copy the .apk to your Android device and open it (you may need to
   allow "install unknown apps" for your file manager/browser).

--------------------------------------------------------
NOTES / LIMITATIONS
--------------------------------------------------------
 - GPU usage % is not exposed by Android without root, so the
   benchmark uses a rendering-based proxy score instead.
 - A true "overlay ON TOP of BGMI while it's running" requires a
   native Android foreground service with SYSTEM_ALERT_WINDOW,
   which is partially scaffolded (the permission + settings intent
   are already wired up) but the in-app floating FPS widget is what
   ships by default since it works reliably everywhere without extra
   native Java/Kotlin service code.
 - All data (sessions, benchmark, profiles) is saved locally in a
   JSON file in the app's data directory.
========================================================
