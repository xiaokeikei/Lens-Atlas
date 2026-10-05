# 镜迹 · Lens Atlas

只读扫描照片与视频，查看相机、镜头、焦距、拍摄时间统计和照片墙。**不修改、删除、移动、重命名原片，不改写 EXIF 或相册结构。**索引、缩略图、扫描记录和登录会话保存在应用自己的数据目录。

## 下载

[手机访问预览版 Release](https://github.com/xiaokeikei/Lens-Atlas/releases/tag/v0.1.8-mobile-access-preview)：Android **0.1.3**，Windows **0.1.8 手机访问预览版**。

| 平台 | 下载 |
| --- | --- |
| 安卓手机 | [安装 APK](https://github.com/xiaokeikei/Lens-Atlas/releases/download/v0.1.8-mobile-access-preview/LensAtlas-0.1.3-android-debug.apk) |
| Windows 10/11 x64 | [完整安装版](https://github.com/xiaokeikei/Lens-Atlas/releases/download/v0.1.8-mobile-access-preview/LensAtlas-0.1.8-mobile-access-preview-Setup-x64.exe) |
| Windows 免安装 | [完整目录 ZIP](https://github.com/xiaokeikei/Lens-Atlas/releases/download/v0.1.8-mobile-access-preview/LensAtlas-mobile-access-preview-windows-x64.zip) |
| 文件校验 | [SHA256SUMS.txt](https://github.com/xiaokeikei/Lens-Atlas/releases/download/v0.1.8-mobile-access-preview/SHA256SUMS.txt) |

NAS Docker 继续使用 [稳定版 0.1.8](https://github.com/xiaokeikei/Lens-Atlas/releases/tag/v0.1.8)，部署说明见 [DOCKER_RELEASES.md](DOCKER_RELEASES.md)。本次不更新 NAS 容器。

## 手机使用

- Android 10 及以上，需要可用的 **Android System WebView**。
- 授权后可扫描全部已授权相册或指定相册，在手机本地统计、筛选和预览；部分照片授权会明确标注范围。
- 连接 NAS：填写镜迹服务地址（默认端口 **52032**）和管理员密码。
- 勾选“保持登录”：加密保存会话，不保存密码。重开自动恢复；会话到期或被服务端撤销后需重新登录。当前服务端记住登录为 30 天。
- “扫描”页可启动、暂停、恢复、取消服务端**已有目录**的只读扫描；关闭手机不停止服务端任务。不开放远程目录增删或原片修改。

## 电脑使用与手机连接

1. 安装前关闭旧镜迹；升级沿用原应用数据。安装版包含运行环境，无需另装 Python、Qt 或媒体读取工具。免安装版需保留整个目录和 `_internal`。
2. 电脑可添加本机或已授权共享目录进行扫描，查看图表、筛选和素材预览。
3. 手机连接电脑：电脑菜单 **手机访问 → 连接本机图库**（Ctrl+M），主动开启访问，保存/复制连接密码并应用设置。默认端口 **52033**。
4. 手机填写电脑窗口显示的地址和**手机连接密码**，勾选保持登录。手机与电脑需在同一局域网或 VPN，电脑镜迹须保持运行，Windows 防火墙需允许程序的专用网络访问。

手机、电脑、NAS 图库分别统计，不上传手机原片，不合并数据库。电脑手机访问默认关闭，可选择下次启动继续开启；查询与扫描复用已有桌面服务及索引。更换电脑连接密码会撤销旧手机会话。

## 数据与限制

- Windows 应用数据默认 `%LOCALAPPDATA%\LensAtlas`；卸载安装版不删除图库索引、设置、缓存和原始素材。
- NAS 素材目录必须只读挂载，应用数据目录与原片分开。建议先使用少量已备份的测试素材验证；索引备份不能代替原片备份。使用风险由用户自行承担，开发者不承担使用造成的损失。
- 当前为开发预览版，Android 使用开发签名、Windows 未做发布者签名。已完成接口、合成扫描、原片哈希和安装/升级/卸载验证；真实大图库、特殊格式、Android 14 部分授权和普通手机全流程仍需实测。
- U30 Air 当前缺少 WebView，不能用于新版界面的实机验收。手机本地扫描首版不保证长期后台运行；视频首版提供系统元数据和缩略图。

## 更多说明

[Android 使用与构建](android/README.md) · [Windows 安装器](installer/README.md) · [详细使用/开发](docs/USAGE.md) · [验证记录](VALIDATION.md) · [更新记录](CHANGELOG.md)
