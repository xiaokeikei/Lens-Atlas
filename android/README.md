# 镜迹 Android · 只读扫描版

Android 0.1.3 客户端，原生只读扫描与本地 React 界面，Android 10（API 29）及以上；需要系统提供可用的 Android System WebView。手机图库与 NAS 图库独立显示，不上传、不合并数据库。

## 使用

1. 安装 APK，点击“授权 / 重新选择可访问照片”。可以授权全部照片与视频，或只授权部分素材。
2. 点击“扫描全部已授权相册”，或“选择指定相册扫描”。仅枚举系统 MediaStore 中已授权、可访问的照片和视频，不遍历其他应用私有目录。
3. 扫描完成后查看统计。相机、镜头、月份、焦距可组合筛选；浏览每页 24 个素材，点击查看元数据与系统缩略图。
4. NAS 需预先部署镜迹并完成管理员初始化。填写镜迹 HTTP/HTTPS 地址和管理员密码。提供三个连接地址槽位；可以勾选保持登录；只保存名称、地址和 Android Keystore 加密的会话令牌，不保存密码。重新打开恢复上次选择的远程图库；网络暂时断开时不删除有效会话。

## 不可违反的只读边界

- 不申请写入媒体、管理媒体或全盘文件管理权限。素材访问只使用 MediaStore 查询、输入流与系统缩略图读取。
- 不修改、不删除、不移动、不重命名任何手机或 NAS 原始照片、视频、EXIF 或相册；不上传、不备份原片。
- SQLite 索引、扫描记录与连接地址只写入 Android 应用私有目录。应用卸载会删除这些应用数据，不影响原始素材。
- 远程网络层采用接口白名单：健康检查、登录/退出、统计与素材查询、目录/任务查询、已有目录增量扫描及任务暂停/恢复/取消。禁止添加/删除目录、素材修改、缓存清理、数据库备份或远程设置修改。登录会在 NAS 服务自己的会话表中产生会话记录；缩略图读取可能由 NAS 服务生成自己的缓存，均不修改素材。
- HTTPS 使用系统证书校验，不接受跳过校验。禁止自动跟随重定向，避免携带令牌跳转。局域网 HTTP 明文连接只适合可信网络；外网使用 VPN 或受信任 HTTPS。

## 扫描与限制

- 索引是上次完成扫描的快照，不是实时文件系统镜像。再次查看时排除当前不可访问的素材；新增素材、修改元数据后需要重新扫描。
- 每次扫描替换当前扫描范围的索引；指定相册扫描不会与上一次范围混合。取消、失败或进程终止时 SQLite 事务回滚，保留上一次完成的索引。
- 首版为前台扫描：切换应用可能继续运行，但没有后台任务保证；退出 App 会取消扫描，系统杀进程后须重新开始。旋转屏幕不会重启扫描。
- 照片元数据由 AndroidX ExifInterface 读取，未记录的字段保持缺失；35mm 等效焦距不使用原生焦距代替。拍摄时间读取 EXIF，缺失时使用系统媒体拍摄时间，不使用文件修改时间。
- 视频首版读取系统索引中的尺寸、拍摄时间与时长；没有复用桌面版 FFprobe。预览为系统缩略图，首版没有视频播放。
- RAW、HEIC 等格式依赖系统 MediaStore 收录、ExifInterface 和系统缩略图支持，不宣称与桌面版 ExifTool/FFmpeg 格式覆盖一致。
- 当前统计从本地索引加载到内存，超大手机图库的性能需要实机验证。NAS 查询、分页由服务端执行。
- 扫描页可以查看远端已有目录，启动/暂停/恢复/取消服务端扫描。扫描任务由服务端执行，关闭手机 App 不会停止服务端任务。

## 构建

需要 Node.js 22+、JDK 17、Android SDK 35、Build Tools 35.0.0。Gradle 8.11.1 / AGP 8.9.1 / Kotlin 2.1.10 固定版本。设置 `JAVA_HOME`、`ANDROID_HOME`，或在 `local.properties` 指定 `sdk.dir`。

```powershell
cd frontend
npm ci
npm run build:mobile
cd ..
New-Item -ItemType Directory -Force android/app/src/main/assets
Copy-Item frontend/dist-mobile/* android/app/src/main/assets -Recurse -Force
cd android
./gradlew.bat testDebugUnitTest lintDebug assembleDebug
```

输出 `app/build/outputs/apk/debug/app-debug.apk` 为开发测试包，使用开发签名，未作为商店正式版本发布。构建不需要真实手机相册或 NAS。

Windows 中文路径可能导致 Gradle Java 测试进程找不到入口类。项目根目录执行 `./scripts/build_android.ps1` 可使用 `%PUBLIC%/LensAtlasAndroidBuild` 下的英文路径构建目录；源文件仍保留于本仓库，APK 复制回 `dist/android`。脚本优先使用 `JAVA_HOME`/`ANDROID_HOME`，也支持本次开发放在 `.runtime/android-tools` 的工具链。

项目根目录执行只读访问静态检查：

```powershell
./.venv/Scripts/python.exe -m pytest -q tests/test_android_readonly.py tests/test_android_webview.py
```

单元测试覆盖 NAS 禁止操作白名单、地址校验、组合筛选和等效焦距缺失语义。实机权限、元数据、缩略图、长时间扫描与 NAS 联调需单独验证；验证记录见 `VALIDATION.md`。

## 合成数据设备集成测试

测试照片只创建于测试 APK 的私有目录，不向手机相册添加素材。NAS 测试服务只使用项目 `.runtime` 中独立生成的合成图库，不连接真实 NAS。测试 APK 不属于分发包，测试 ContentProvider 不包含在主 APK 中。

```powershell
./scripts/build_android.ps1 -IncludeInstrumentation
./.venv/Scripts/python.exe scripts/verify_android_nas_server.py
# 另一个终端，以下命令仅在授权的测试设备上执行：
adb install -r dist/android/LensAtlas-0.1.3-android-debug.apk
adb install -r dist/android/app-debug-androidTest.apk
adb reverse tcp:18767 tcp:18767
adb shell am instrument -w -e nasUrl http://127.0.0.1:18767 app.lensatlas.android.test/androidx.test.runner.AndroidJUnitRunner
```

覆盖指定相册、EXIF、缺失等效焦距、取消事务回滚、扫描前后 SHA-256、实际 NAS API 登录/统计/筛选/详情/签名缩略图。未指定 `nasUrl` 时跳过 NAS 联调测试。测试完成后停止本机合成服务、移除测试 APK 并撤销本次测试的端口反向转发；保留主 App 的行为由设备用户决定。


## 0.1.1 手机界面

- 与网页/PC 共用 `LibraryWidgets.tsx` 的统计卡片、ECharts 相机/镜头/拍摄时间图，以及 `FocalChart.tsx` 的焦距区间和具体值图；共用原有配色、卡片和照片墙样式。
- 顶部切换手机/NAS 图库，底部为总览、素材、扫描、连接四个入口；手机总览使用两列指标卡片，照片墙两列分页，较宽屏幕自动增加列数。
- React 界面随 APK 离线打包，仅通过固定动作的原生桥访问索引和只读 NAS 客户端。NAS 管理网页不会加载进 WebView；外部资源、文件访问、任意导航和网页网络访问均禁止，NAS 请求仍由原生接口白名单控制。
- U30 Air 当前没有可用 WebView，无法呈现新版界面；会显示缺失组件说明而非崩溃。没有为随身 Wi-Fi 安装浏览器或修改系统组件。普通 Android 手机仍需进行最终显示、授权及长时间扫描验证。
- 浏览器界面检查：`npx playwright test --config playwright.mobile.config.ts`（在 frontend 目录），使用明确标记的合成数据，覆盖 320/390 像素宽布局、图表筛选、照片墙/详情、NAS 连接状态及指定相册扫描参数。


## 0.1.2 保持登录与服务端扫描

升级后登录一次并勾选“保持登录”。会话令牌使用 Android Keystore AES-GCM 加密，并绑定连接槽位和服务地址；不保存密码，不把令牌交给网页界面，禁用备份/迁移。重新打开恢复上次远程图库；会话有效期由服务端返回（当前镜迹记住登录为 30 天），到期、被服务端撤销或本机忘记登录后需要重新登录。连接页可编辑地址和忘记保存的登录。改变地址需重新验证，不将凭据自动发送给新地址。

## 0.1.3 连接电脑本机图库

1. 关闭正在运行的旧电脑镜迹，解压 `LensAtlas-mobile-access-preview-windows-x64.zip`，运行其中的 `LensAtlas/LensAtlas.exe`。保留整个目录和 `_internal`；默认沿用 `%LOCALAPPDATA%/LensAtlas` 的本机图库数据。
2. 电脑窗口选择“手机访问 → 连接本机图库”（Ctrl+M），勾选允许手机访问，保存/复制首次显示的连接密码并应用设置。默认端口 52033；手机与电脑需在同一局域网或 VPN，Windows 防火墙需允许程序的专用网络访问。
3. 手机“连接”中填写窗口显示的地址、名称与手机连接密码。NAS 使用 NAS 管理员密码，电脑使用单独的手机连接密码；勾选保持登录即可自动恢复。
4. 电脑镜迹须保持运行。查询、缩略图和扫描任务复用电脑现有服务与数据库，不另起图库数据库，不合并手机/NAS/电脑图库。访问入口默认关闭；可主动选择下次启动继续允许访问。
5. 手机只能扫描电脑已经添加的目录，不能远程添加/移除目录、修改/删除原片或修改电脑缓存/备份设置。修改电脑连接密码会撤销所有手机会话。关闭电脑端手机访问入口只停止接收连接；电脑扫描任务由现有桌面服务维护。

电脑访问入口仅提供受限 API，不提供远程管理网页，也不暴露电脑本机会话令牌。电脑预览包基于公开 0.1.8，作为手机访问预览版发布；Android 0.1.3 已包含 0.1.2 的保持登录和 NAS 扫描功能。
