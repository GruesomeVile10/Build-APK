@echo off
setlocal enabledelayedexpansion
title BGMI Performance Monitor - APK Builder Helper
color 0A

echo ============================================================
echo   BGMI Performance Monitor - APK Build Helper (Windows)
echo ============================================================
echo.
echo  IMPORTANT: Buildozer/python-for-android does NOT support
echo  compiling APKs natively on Windows, and this tool avoids
echo  requiring WSL or a Linux VM on your PC.
echo.
echo  Instead, this script prepares your files and uses
echo  GOOGLE COLAB (a free, cloud Python/Jupyter environment)
echo  to run Buildozer for you - 100%% via Python, nothing to
echo  install locally besides a web browser.
echo ============================================================
echo.

REM --- Step 1: check python is available (used only to zip files) ---
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [WARN] Python was not found in PATH. Skipping auto-zip step.
    goto :open_colab
)

echo [1/2] Packaging main.py + buildozer.spec into bgmi_apk_project.zip ...
python -c "import zipfile,os; z=zipfile.ZipFile('bgmi_apk_project.zip','w'); [z.write(f) for f in ['main.py','buildozer.spec'] if os.path.exists(f)]; z.close(); print('Created bgmi_apk_project.zip')"
echo.

:open_colab
echo [2/2] Opening the build instructions and Google Colab in your browser...
echo.
echo   1. In the Colab tab that opens, choose:  File ^> Upload notebook
echo   2. Upload the file:  Build_APK_On_Colab.ipynb  (included in this folder)
echo   3. Run each cell top to bottom.
echo   4. When prompted, upload:  main.py  and  buildozer.spec
echo      (or just unzip bgmi_apk_project.zip that was created next to this .bat)
echo   5. Wait for the build to finish, then the notebook will download
echo      the finished .apk file straight to your PC automatically.
echo.
start "" "https://colab.research.google.com/"
start "" "%~dp0Build_APK_On_Colab.ipynb"

echo ============================================================
echo  Alternative (build directly ON an Android phone, no PC at all):
echo   1. Install "Termux" from F-Droid on your Android phone.
echo   2. Inside Termux run:
echo        pkg update ^&^& pkg upgrade
echo        pkg install python git openjdk-17 -y
echo        pip install buildozer cython
echo        buildozer android debug
echo   3. The APK appears in the "bin" folder inside your project.
echo ============================================================
echo.
pause
