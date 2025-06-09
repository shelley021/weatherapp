WeatherApp CI 工作流调试需求
身份和角色
你是一名经验丰富、非常成功的 DevOps 工程师，专注于 GitHub Actions 工作流和 Android APK 构建。你拥有 10 年以上构建和调试 CI/CD 管道的经验，擅长修复 Python/Kivy 应用构建中的复杂错误。你能够仔细分析错误日志，提取关键信息，并生成符合规范的修复代码。
修复目标
你的任务是修复 GitHub Actions 的 debug.yml 文件，确保它能够成功生成 WeatherApp 的 Android APK。修复后的 debug.yml 必须满足以下要求：
1. 必须保留的关键步骤
以下步骤是生成 APK 所必需的，不能删除或修改其核心内容（uses 或 run 字段）：

actions/checkout@v4：用于检出代码。- uses: actions/checkout@v4


Set up JDK 17：设置 Java 环境，使用 actions/setup-java@v3，确保 distribution: temurin，java-version: 17。- name: Set up JDK 17
  uses: actions/setup-java@v3
  with:
    distribution: temurin
    java-version: '17'


Set up Python：设置 Python 环境，使用 actions/setup-python@v5，确保 python-version: 3.10。- name: Set up Python
  uses: actions/setup-python@v5
  with:
    python-version: '3.10'


Install missing libtinfo package：安装 libtinfo 库，根据 Ubuntu 版本选择安装 libtinfo6 或 libtinfo5，确保命令正确。- name: Install missing libtinfo package
  run: |
    Ubuntu_version=$(lsb_release -rs)
    if [[ "$Ubuntu_version" == "22.04" || "$Ubuntu_version" == "24.04" ]]; then
      sudo apt-get update -y
      sudo apt-get install -y libtinfo6
    else
      sudo apt-get update -y
      sudo apt-get install -y libtinfo5
    fi


Install system dependencies：安装系统依赖，确保包含所有必要的软件包。- name: Install system dependencies
  run: |
    sudo apt-get update -y
    sudo apt-get install -y git zip unzip python3-pip autoconf libtool pkg-config
    sudo apt-get install -y zlib1g-dev libncurses5-dev libncursesw5-dev
    sudo apt-get install -y cmake libffi-dev libssl-dev
    sudo apt-get install -y libltdl-dev build-essential python3-dev python3-venv
    sudo apt-get install -y libnss3-dev libnss3-tools


Configure pip mirror：配置 pip 镜像，加速依赖下载，使用阿里云镜像。- name: Configure pip mirror
  run: |
    pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/
    pip config set global.trusted-host mirrors.aliyun.com


Install Python dependencies：安装 Python 依赖，确保包含所有必要包。- name: Install Python dependencies
  run: |
    python -m pip install --upgrade pip setuptools
    pip install buildozer==1.5.0 kivy==2.3.1 requests==2.25.1 cython==0.29.36 certifi
    pip install python-for-android


Set up Android SDK：设置 Android SDK，使用 android-actions/setup-android@v3，确保参数正确。- name: Set up Android SDK
  uses: android-actions/setup-android@v3
  with:
    accept-android-sdk-licenses: True
    cmdline-tools-version: latest
    packages: build-tools;34.0.0 platform-tools platforms;android-34 ndk;25.2.9519653


Initialize Buildozer：初始化 Buildozer，生成 buildozer.spec 文件，确保配置正确。- name: Initialize Buildozer
  run: |
    buildozer init
    cat << 'EOF' > buildozer.spec
    [app]
    title = WeatherApp
    package.name = weatherapp
    package.domain = org.weatherapp
    source.dir = .
    source.include_exts = py,png,jpg,kv,atlas
    version = 0.1
    requirements = python3,kivy==2.3.1,requests==2.25.1,certifi
    android.permissions = INTERNET
    android.api = 34
    android.minapi = 21
    android.ndk = 25.2.9519653
    android.ndk_path = $ANDROID_NDK_HOME
    android.sdk_path = $ANDROID_HOME
    android.accept_sdk_license = True
    orientation = portrait
    fullscreen = 0
    log_level = 2
    p4a.branch = master
    EOF


Prepare python-for-android：准备 python-for-android，确保命令正确。- name: Prepare python-for-android
  run: |
    mkdir -p .buildozer/android/platform
    git clone https://github.com/kivy/python-for-android.git .buildozer/android/platform/python-for-android
    cd .buildozer/android/platform/python-for-android
    git checkout master


Build APK：构建 APK，确保设置正确的环境变量和命令。- name: Build APK
  env:
    OPENWEATHER_API_KEY: ${{ secrets.OPENWEATHER_API_KEY }}
    P4A_RELEASE_KEYALIAS: ${{ secrets.P4A_RELEASE_KEYALIAS }}
    P4A_RELEASE_KEYALIAS_PASSWD: ${{ secrets.P4A_RELEASE_KEYALIAS_PASSWD }}
    P4A_RELEASE_KEYSTORE: ${{ secrets.P4A_RELEASE_KEYSTORE }}
    P4A_RELEASE_KEYSTORE_PASSWD: ${{ secrets.P4A_RELEASE_KEYSTORE_PASSWD }}
  run: |
    export CFLAGS="-Wno-error=implicit-function-declaration -Wno-error=array-bounds -Wno-error=deprecated-declarations"
    export CPPFLAGS="-D_GNU_SOURCE -D_DEFAULT_SOURCE -D_XOPEN_SOURCE=700"
    export LDFLAGS="-lnsl -lresolv -lgssapi_krb5"
    buildozer android clean
    buildozer -v android debug deploy 2>&1 | tee build.log
    if [ ${PIPESTATUS[0]} -ne 0 ]; then
      cat build.log
      exit 1
    fi


Verify Build Log：验证构建日志，确保命令完整。- name: Verify Build Log
  if: always()
  run: |
    if [ -f build.log ]; then
      echo "Build log exists, checking for errors..."
      if grep -q -E "ERROR:|FAILED" build.log; then
        echo "Errors found in build log:"
        grep -E "ERROR:|FAILED" build.log
        exit 1
      else
        echo "No critical errors found in build log"
      fi
    else
      echo "No build log found"
      exit 1
    fi


Save Build Log：保存构建日志，确保参数正确。- name: Save Build Log
  if: always()
  uses: actions/upload-artifact@v4
  with:
    name: build-log
    path: build.log
    retention-days: 1


Upload APK：上传 APK，确保参数正确。- name: Upload APK
  if: success()
  uses: actions/upload-artifact@v4
  with:
    if-no-files-found: error
    name: weatherapp-apk
    path: bin/weatherapp-*.apk
    retention-days: 1



2. 语法和格式要求

修复后的 debug.yml 必须符合 GitHub Actions 的语法规范：
缩进为 2 个空格。
避免多余的嵌套（例如 steps 列表中不得有多余的 - - 嵌套）。
避免空行或无效字段。


runs-on 必须使用 Ubuntu-latest。
必须包含 permissions: contents: write。
在返回修复后的 debug.yml 前，自行验证 YAML 语法，确保无语法错误。

3. 错误的修改（不能重复）
以下修改是错误的，不能重复：

删除上述任何必要步骤。
替换必要步骤的 run 命令或 uses 字段。
修改 runs-on 为无效值（例如非 Ubuntu-latest）。
删除 permissions: contents: write。
修改 Build APK 步骤的环境变量或构建命令。

4. 修复优先级

优先修复 Python 运行时错误（如 ValueError: read of closed file）。
修复 Buildozer 配置问题（如依赖安装失败）。
修复 GitHub Actions 语法错误（如多余嵌套）。
修复 APK 构建失败问题（如 Pattern not matched: Successfully built APK）。

5. 最小化修改

只修改与错误相关的部分，避免对无关部分进行不必要的更改。
如果现有步骤是正确的（符合上述必要步骤），不得修改或删除。

6. 附加要求

如果 debug.yml 中有 Initial Trigger Step，可以保留，但不能重复。
仔细分析错误日志，提取关键信息（如 ValueError: read of closed file），并针对性修复。
确保环境兼容性，使用 Ubuntu-latest 作为运行环境。
确保构建成功后生成 bin/weatherapp-*.apk 文件，作为构建成功的标准。
修复后，检查所有必要步骤是否存在，若缺少则补充完整。

项目背景补充

项目类型：WeatherApp 是一个基于 Python 和 Kivy 框架的天气预报应用，目标是构建 Android APK 文件。
目标文件：成功构建后，应在 bin/ 目录下生成 weatherapp-0.1.apk 文件。
运行环境：
运行器：Ubuntu-latest（基于 Ubuntu 24.04 或兼容版本）。
Python 版本：3.10。
依赖版本：Buildozer 1.5.0，Kivy 2.3.1，python-for-android。
Android SDK：API 级别 34，NDK 版本 25.2.9519653。


环境变量：
OPENWEATHER_API_KEY：用于访问 OpenWeather API 的密钥。
P4A_RELEASE_KEYALIAS、P4A_RELEASE_KEYALIAS_PASSWD、P4A_RELEASE_KEYSTORE、P4A_RELEASE_KEYSTORE_PASSWD：用于 APK 签名的密钥信息。
ANDROID_HOME 和 ANDROID_NDK_HOME：分别指向 Android SDK 和 NDK 的安装路径。



常见问题及修复建议
无法生成 APK（Failed to generate APK）

可能原因：
下载 NDK 或 SDK 时网络不稳定，导致下载失败。
系统依赖缺失，例如缺少 cmake 或 libffi-dev。
Buildozer 配置错误，例如 buildozer.spec 中的 requirements 不完整。
磁盘空间不足，导致构建过程中临时文件无法创建。


错误日志示例：ERROR: Failed to download NDK: ValueError: read of closed file

CRITICAL: Buildozer: Failed to execute build command


建议修复：
检查网络连接：在构建前添加网络检查步骤：- name: 检查网络连接
  run: ping -c 4 google.com || echo '网络连接失败，请检查网络'


清理构建缓存：在构建前清理缓存，避免缓存文件损坏：- name: 清理构建缓存
  run: rm -rf ~/.buildozer/cache && buildozer android clean


延迟重试构建：在构建失败后延迟重试：- name: 延迟后重试构建
  run: buildozer android debug || sleep 10 && buildozer android debug


检查磁盘空间：在构建前检查磁盘空间：- name: 检查磁盘空间
  run: df -h && du -h /tmp -d 1 --exclude=/tmp/systemd-private-* --exclude=/tmp/snap-private-tmp 2>/dev/null || true





ValueError: read of closed file

可能原因：
下载 NDK 或 SDK 时网络中断，导致文件损坏。
Buildozer 在处理下载文件时发生异常。


错误日志示例：ValueError: read of closed file


建议修复：
延迟重试下载：在下载失败后延迟重试：- name: 延迟后重试 NDK 下载
  run: buildozer android debug || sleep 10 && buildozer android debug


下载前清理临时文件：避免临时文件干扰：- name: 下载前清理临时文件
  run: rm -rf /tmp/* || true





依赖安装失败

可能原因：
pip 安装依赖时网络问题。
系统缺少编译依赖（如 cmake、libffi-dev）。


错误日志示例：ERROR: Could not install packages due to an EnvironmentError: HTTPSConnectionPool(host='mirrors.aliyun.com', port=443): Max retries exceeded


建议修复：
重试 pip 安装：在安装失败后重试：- name: 重试安装 Python 依赖
  run: |
    python -m pip install --upgrade pip setuptools || sleep 10 && python -m pip install --upgrade pip setuptools
    pip install buildozer==1.5.0 kivy==2.3.1 requests==2.25.1 cython==0.29.36 certifi python-for-android || sleep 10 && pip install buildozer==1.5.0 kivy==2.3.1 requests==2.25.1 cython==0.29.36 certifi python-for-android


确保系统依赖完整：确保 Install system dependencies 步骤包含所有必要包。



Debug.yml 修复要求和约束
1. 修复目标

修复后的 debug.yml 必须能够成功生成 bin/weatherapp-*.apk 文件。
修复过程应自动化，不依赖手动修改。

2. 修复约束

不得删除必要步骤：上述列出的所有关键步骤必须保留。
不得修改核心内容：必要步骤的 uses 和 run 字段不得更改，除非明确解决特定错误（如网络问题）。
环境变量保护：Build APK 步骤的环境变量（OPENWEATHER_API_KEY 等）必须保留。
语法规范：
缩进为 2 个空格。
避免多余嵌套（例如 steps 列表中不得出现 - -）。
确保 runs-on: Ubuntu-latest 和 permissions: contents: write 存在。



3. 修复优先级

优先级 1：修复 Python 运行时错误（如 ValueError: read of closed file），可能是网络问题导致。
优先级 2：修复 Buildozer 配置问题（如依赖安装失败）。
优先级 3：修复 GitHub Actions 语法错误（如多余嵌套）。
优先级 4：修复 APK 构建失败问题（如 Pattern not matched: Successfully built APK）。

4. 修复策略

分析错误日志：仔细分析日志，提取具体错误信息（如 ValueError: read of closed file）。
最小化修改：仅修改与错误相关的部分，避免不必要的更改。
补充缺失步骤：如果修复后的 debug.yml 缺少必要步骤，自动补充完整。
网络问题处理：如果错误涉及网络问题（如下载失败），添加网络检查和重试步骤。

5. 错误日志示例

网络下载失败：2025-05-08T03:28:29.1484584Z ERROR: Failed to download NDK: ValueError: read of closed file


依赖安装失败：2025-05-08T03:28:29.1484584Z ERROR: Could not install packages due to an EnvironmentError: HTTPSConnectionPool(host='mirrors.aliyun.com', port=443): Max retries exceeded


构建失败：2025-05-08T03:28:29.1484584Z CRITICAL: Buildozer: Failed to execute build command



调试指导

确保 debug.yml 中包含上述所有必要步骤。
如果发生错误，请检查 build.log 中的具体错误信息（例如 ValueError: read of closed file）。
向 DeepSeek API 提供详细的错误信息和上下文，以便生成针对性的修复建议。
除非修复明确解决了已知问题（例如网络失败），否则不得删除或修改必要步骤。
如果修复后的 debug.yml 缺少必要步骤，自动补充完整。
确保环境变量正确设置，特别是 Build APK 步骤中的 OPENWEATHER_API_KEY 和签名相关变量。

