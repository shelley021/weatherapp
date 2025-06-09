def load_error_patterns():
    """加载错误模式，直接返回默认错误模式列表"""
    default_patterns = [
        # 优先匹配具体的 ValueError: read of closed file
        {
            "pattern": r"ValueError: read of closed file",
            "fix": {
                "step_name": "Retry NDK Download with Delay",
                "step_code": """
        - name: Retry NDK Download with Delay
          run: buildozer android debug || sleep 10 && buildozer android debug
"""
            }
        },
        {
            "pattern": r"sdkmanager: command not found",
            "fix": {
                "step_name": "Install Android SDK Tools",
                "step_code": """
        - name: Install Android SDK Tools
          run: |
            sdkmanager --install "cmdline-tools;latest"
            sdkmanager --install "build-tools;33.0.0"
            sdkmanager --install "platforms;android-33"
            sdkmanager --install "platform-tools"
            echo "ANDROID_HOME=$ANDROID_HOME" >> $GITHUB_ENV
            echo "PATH=$PATH:$ANDROID_HOME/cmdline-tools/latest/bin" >> $GITHUB_ENV
            echo "PATH=$PATH:$ANDROID_HOME/platform-tools" >> $GITHUB_ENV
"""
            }
        },
        {
            "pattern": r"Could not determine java version|java: command not found",
            "fix": {
                "step_name": "Set up JDK 17",
                "step_code": """
        - name: Set up JDK 17
          uses: actions/setup-java@v4
          with:
            java-version: '17'
            distribution: 'temurin'
"""
            }
        },
        {
            "pattern": r"No such file or directory:.*gradlew",
            "fix": {
                "step_name": "Make gradlew executable",
                "step_code": """
        - name: Make gradlew executable
          run: chmod +x ./gradlew
"""
            }
        },
        {
            "pattern": r"Invalid workflow file",
            "fix": {
                "step_name": "Fix workflow file",
                "step_code": None
            }
        },
        {
            "pattern": r"Unexpected value '(\w+)'",
            "fix": {
                "step_name": "Fix unexpected value",
                "step_code": None
            }
        },
        {
            "pattern": r"Buildozer NDK download failed: (timeout|connection|closed file)",
            "fix": {
                "step_name": "Check Network and Retry NDK Download",
                "step_code": """
        - name: Check Network and Retry NDK Download
          run: ping -c 4 google.com || echo '网络连接失败，请检查网络'; rm -rf /tmp/* && buildozer android debug
"""
            }
        },
        {
            "pattern": r"urllib.request.retrieve failed",
            "fix": {
                "step_name": "Set Network Proxy",
                "step_code": """
        - name: Set Network Proxy
          run: export HTTP_PROXY=http://proxy.example.com:8080 && export HTTPS_PROXY=http://proxy.example.com:8080
"""
            }
        },
        {
            "pattern": r"Pattern not matched: Successfully built APK",
            "fix": {
                "step_name": "Verify Buildozer Config",
                "step_code": """
        - name: Verify Buildozer Config
          run: buildozer android debug --verbose
"""
            }
        },
        {
            "pattern": r"No space left on device",
            "fix": {
                "step_name": "Clean Disk Space",
                "step_code": """
        - name: Clean Disk Space
          run: rm -rf /tmp/* && docker system prune -a --force
"""
            }
        },
        {
            "pattern": r"tempfile.*closed",
            "fix": {
                "step_name": "Clean Temp Files Before Download",
                "step_code": """
        - name: Clean Temp Files Before Download
          run: rm -rf /tmp/* || true
"""
            }
        },
        {
            "pattern": r"buildozer.*download.*failed",
            "fix": {
                "step_name": "Use Cached NDK",
                "step_code": """
        - name: Use Cached NDK
          run: buildozer android use_cached_ndk
"""
            }
        },
        {
            "pattern": r"urllib.*timeout",
            "fix": {
                "step_name": "Set Download Timeout",
                "step_code": """
        - name: Set Download Timeout
          run: export BUILDOCZER_TIMEOUT=600
          env:
            BUILDOCZER_TIMEOUT: 600
"""
            }
        },
        {
            "pattern": r"DNS resolution failed",
            "fix": {
                "step_name": "Set Network Proxy",
                "step_code": """
        - name: Set Network Proxy
          run: export HTTP_PROXY=http://proxy.example.com:8080 && export HTTPS_PROXY=http://proxy.example.com:8080
"""
            }
        },
        {
            "pattern": r"du: cannot read directory.*Permission denied",
            "fix": {
                "step_name": "Skip Permission Denied Directories",
                "step_code": """
        - name: Check Disk Space Before Build
          run: df -h && du -h /tmp -d 1 --exclude=/tmp/systemd-private-* --exclude=/tmp/snap-private-tmp 2>/dev/null || true
"""
            }
        },
        {
            "pattern": r".*permission denied.*",
            "fix": {
                "step_name": "Skip Permission Denied Directories",
                "step_code": """
        - name: Check Disk Space Before Build
          run: df -h && du -h /tmp -d 1 --exclude=/tmp/systemd-private-* --exclude=/tmp/snap-private-tmp 2>/dev/null || true
"""
            }
        },
        {
            "pattern": r".*error.*exit code 1.*",
            "fix": {
                "step_name": "Clean Build Cache and Retry",
                "step_code": """
        - name: Clean Build Cache and Retry
          run: rm -rf ~/.buildozer/cache && buildozer android clean && buildozer android debug
"""
            }
        },
        {
            "pattern": r".*buildozer.*error.*",
            "fix": {
                "step_name": "Verify Buildozer Config",
                "step_code": """
        - name: Verify Buildozer Config
          run: buildozer android debug --verbose
"""
            }
        },
        {
            "pattern": r".*compile error.*",
            "fix": {
                "step_name": "Clean Build Cache and Retry",
                "step_code": """
        - name: Clean Build Cache and Retry
          run: rm -rf ~/.buildozer/cache && buildozer android clean && buildozer android debug
"""
            }
        },
        {
            "pattern": r".*build error.*",
            "fix": {
                "step_name": "Clean Build Cache and Retry",
                "step_code": """
        - name: Clean Build Cache and Retry
          run: rm -rf ~/.buildozer/cache && buildozer android clean && buildozer android debug
"""
            }
        },
        {
            "pattern": r".*warning.*",
            "fix": {
                "step_name": None,
                "step_code": None
            }
        },
        {
            "pattern": r".*WARNING:.*",
            "fix": {
                "step_name": None,
                "step_code": None
            }
        },
        {
            "pattern": r".*except.*",
            "fix": {
                "step_name": "Clean Build Cache and Retry",
                "step_code": """
        - name: Clean Build Cache and Retry
          run: rm -rf ~/.buildozer/cache && buildozer android clean && buildozer android debug
"""
            }
        },
        {
            "pattern": r".*EXCEPT:.*",
            "fix": {
                "step_name": "Clean Build Cache and Retry",
                "step_code": """
        - name: Clean Build Cache and Retry
          run: rm -rf ~/.buildozer/cache && buildozer android clean && buildozer android debug
"""
            }
        },
        {
            "pattern": r".*connection refused.*",
            "fix": {
                "step_name": "Set Network Proxy",
                "step_code": """
        - name: Set Network Proxy
          run: export HTTP_PROXY=http://proxy.example.com:8080 && export HTTPS_PROXY=http://proxy.example.com:8080
"""
            }
        },
        {
            "pattern": r".*timeout.*",
            "fix": {
                "step_name": "Set Download Timeout",
                "step_code": """
        - name: Set Download Timeout
          run: export BUILDOCZER_TIMEOUT=600
          env:
            BUILDOCZER_TIMEOUT: 600
"""
            }
        },
        {
            "pattern": r".*pip install failed.*",
            "fix": {
                "step_name": "Update Dependencies",
                "step_code": """
        - name: Update Dependencies
          run: pip install --upgrade pip setuptools kivy buildozer
"""
            }
        },
        {
            "pattern": r".*npm install failed.*",
            "fix": {
                "step_name": None,
                "step_code": None
            }
        },
        {
            "pattern": r".*gradle build failed.*",
            "fix": {
                "step_name": "Clean Build Cache",
                "step_code": """
        - name: Clean Build Cache
          run: rm -rf ~/.buildozer/cache && buildozer android clean
"""
            }
        },
        {
            "pattern": r".*maven build failed.*",
            "fix": {
                "step_name": "Clean Build Cache",
                "step_code": """
        - name: Clean Build Cache
          run: rm -rf ~/.buildozer/cache && buildozer android clean
"""
            }
        },
        {
            "pattern": r".*could not resolve host.*",
            "fix": {
                "step_name": "Set Network Proxy",
                "step_code": """
        - name: Set Network Proxy
          run: export HTTP_PROXY=http://proxy.example.com:8080 && export HTTPS_PROXY=http://proxy.example.com:8080
"""
            }
        },
        {
            "pattern": r".*Traceback.*",
            "fix": {
                "step_name": "Clean Build Cache and Retry",
                "step_code": """
        - name: Clean Build Cache and Retry
          run: rm -rf ~/.buildozer/cache && buildozer android clean && buildozer android debug
"""
            }
        },
        {
            "pattern": r"Access denied",
            "fix": {
                "step_name": "Skip Permission Denied Directories",
                "step_code": """
        - name: Check Disk Space Before Build
          run: df -h && du -h /tmp -d 1 --exclude=/tmp/systemd-private-* --exclude=/tmp/snap-private-tmp 2>/dev/null || true
"""
            }
        },
        {
            "pattern": r"Disk quota exceeded",
            "fix": {
                "step_name": "Clean Disk Space",
                "step_code": """
        - name: Clean Disk Space
          run: rm -rf /tmp/* && docker system prune -a --force
"""
            }
        },
        {
            "pattern": r"ImportError",
            "fix": {
                "step_name": "Update Dependencies",
                "step_code": """
        - name: Update Dependencies
          run: pip install --upgrade pip setuptools kivy buildozer
"""
            }
        },
        {
            "pattern": r"ModuleNotFoundError",
            "fix": {
                "step_name": "Update Dependencies",
                "step_code": """
        - name: Update Dependencies
          run: pip install --upgrade pip setuptools kivy buildozer
"""
            }
        },
        {
            "pattern": r"SyntaxError",
            "fix": {
                "step_name": "Clean Build Cache and Retry",
                "step_code": """
        - name: Clean Build Cache and Retry
          run: rm -rf ~/.buildozer/cache && buildozer android clean && buildozer android debug
"""
            }
        },
        {
            "pattern": r"Rate limit exceeded",
            "fix": {
                "step_name": None,
                "step_code": None
            }
        },
        {
            "pattern": r"No such file or directory",
            "fix": {
                "step_name": "Create Missing Directory",
                "step_code": """
        - name: Create Missing Directory
          run: mkdir -p $ANDROID_HOME/ndk
"""
            }
        },
        {
            "pattern": r"License not accepted",
            "fix": {
                "step_name": "Accept Android Licenses",
                "step_code": """
        - name: Accept Android Licenses
          run: yes | $ANDROID_HOME/cmdline-tools-latest/bin/sdkmanager --sdk_root=$ANDROID_HOME --licenses
"""
            }
        },
        {
            "pattern": r"Invalid syntax in buildozer.spec",
            "fix": {
                "step_name": "Initialize Buildozer",
                "step_code": """
        - name: Initialize Buildozer
          run: buildozer init
          cat << 'EOF' > buildozer.spec
[app]
title = WeatherApp
package.name = weatherapp
package.domain = org.weatherapp
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 0.1
requirements = python3,kivy==2.3.1,requests==2.25.1,sdl2_ttf==2.0.18,certifi
android.permissions = INTERNET
android.api = 33
android.minapi = 21
android.ndk = 25c
android.ndk_path = ${ANDROID_NDK_HOME}
android.accept_sdk_license = True
orientation = portrait
fullscreen = 0
log_level = 2
p4a.branch = master
EOF
"""
            }
        },
        {
            "pattern": r"Failed to download.*repository",
            "fix": {
                "step_name": "Set Network Proxy",
                "step_code": """
        - name: Set Network Proxy
          run: export HTTP_PROXY=http://proxy.example.com:8080 && export HTTPS_PROXY=http://proxy.example.com:8080
"""
            }
        },
        {
            "pattern": r"Could not resolve dependencies",
            "fix": {
                "step_name": "Update Package Index",
                "step_code": """
        - name: Update Package Index
          run: sudo apt-get update --allow-insecure-repositories
"""
            }
        },
        {
            "pattern": r"Out of memory",
            "fix": {
                "step_name": "Increase Swap Space",
                "step_code": """
        - name: Increase Swap Space
          run: sudo fallocate -l 2G /swapfile
          sudo chmod 600 /swapfile
          sudo mkswap /swapfile
          sudo swapon /swapfile
"""
            }
        },
        {
            "pattern": r"buildozer: command not found",
            "fix": {
                "step_name": "Install Buildozer",
                "step_code": """
        - name: Install Buildozer
          run: pip install buildozer==1.5.0
"""
            }
        },
        {
            "pattern": r"java: command not found",
            "fix": {
                "step_name": "Install Java",
                "step_code": """
        - name: Install Java
          run: sudo apt-get install -y openjdk-17-jdk
"""
            }
        },
        {
            "pattern": r"cmake: command not found",
            "fix": {
                "step_name": "Install CMake",
                "step_code": """
        - name: Install CMake
          run: sudo apt-get install -y cmake
"""
            }
        },
        {
            "pattern": r"unzip: command not found",
            "fix": {
                "step_name": "Install Unzip",
                "step_code": """
        - name: Install Unzip
          run: sudo apt-get install -y unzip
"""
            }
        },
        {
            "pattern": r"wget: command not found",
            "fix": {
                "step_name": "Install Wget",
                "step_code": """
        - name: Install Wget
          run: sudo apt-get install -y wget
"""
            }
        },
        {
            "pattern": r"E: Unable to locate package.*",
            "fix": {
                "step_name": "Update Package Index",
                "step_code": """
        - name: Update Package Index
          run: sudo apt-get update --allow-insecure-repositories
"""
            }
        },
        {
            "pattern": r"No event triggers defined in [`']on[`']",
            "fix": {
                "step_name": "Fix workflow file",
                "step_code": None
            }
        },
        {
            "pattern": r"No buildozer\.spec found",
            "fix": {
                "step_name": "Initialize Buildozer",
                "step_code": """
        - name: Initialize Buildozer
          run: buildozer init
          cat << 'EOF' > buildozer.spec
[app]
title = WeatherApp
package.name = weatherapp
package.domain = org.weatherapp
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 0.1
requirements = python3,kivy==2.3.1,requests==2.25.1,sdl2_ttf==2.0.18,certifi
android.permissions = INTERNET
android.api = 33
android.minapi = 21
android.ndk = 25c
android.ndk_path = ${ANDROID_NDK_HOME}
android.accept_sdk_license = True
orientation = portrait
fullscreen = 0
log_level = 2
p4a.branch = master
EOF
"""
            }
        },
        {
            "pattern": r"Unexpected value 'true'",
            "fix": {
                "step_name": "Fix unexpected value",
                "step_code": None
            }
        },
        {
            "pattern": r"runs-on.*not supported",
            "fix": {
                "step_name": "Fix workflow file",
                "step_code": None
            }
        },
        {
            "pattern": r"No steps executed",
            "fix": {
                "step_name": "Add Checkout",
                "step_code": """
        - name: Add Checkout
          uses: actions/checkout@v4
"""
            }
        },
        {
            "pattern": r"No files were found with the provided path: bin/\*.apk",
            "fix": {
                "step_name": "Verify Buildozer Config",
                "step_code": """
        - name: Verify Buildozer Config
          run: buildozer android debug --verbose
"""
            }
        },
        {
            "pattern": r"Unexpected input\(s\).*valid inputs are",
            "fix": {
                "step_name": "Fix workflow file",
                "step_code": None
            }
        },
        {
            "pattern": r"ndk.*not found",
            "fix": {
                "step_name": "Force NDK Redownload",
                "step_code": """
        - name: Force NDK Redownload
          run: rm -rf ~/.buildozer/android/platform/android-ndk-* && buildozer android debug
"""
            }
        },
        {
            "pattern": r"buildozer.*version.*not compatible",
            "fix": {
                "step_name": "Update Dependencies",
                "step_code": """
        - name: Update Dependencies
          run: pip install --upgrade pip setuptools kivy buildozer
"""
            }
        },
        {
            "pattern": r"E: The update command takes no arguments",
            "fix": {
                "step_name": "Update Package Index",
                "step_code": """
        - name: Update Package Index
          run: sudo apt-get update --allow-insecure-repositories
"""
            }
        }
    ]

    print(f"[DEBUG] 返回默认错误模式，共 {len(default_patterns)} 个")
    return default_patterns