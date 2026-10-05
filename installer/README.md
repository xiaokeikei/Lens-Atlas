# Windows 安装包

安装版与绿色版使用同一份通过桌面烟雾验证的程序。应用仍为 PySide6 / Qt WebEngine，包内包含 Python 和媒体读取工具，终端用户无需安装开发环境。

## 安装约定

- 当前用户安装，不请求管理员权限。
- 默认程序目录：`%LOCALAPPDATA%\Programs\LensAtlas`；安装向导可选择其他可写本地目录，例如 `D:\Apps\LensAtlas`。
- 数据仍为 `%LOCALAPPDATA%\LensAtlas`，与绿色版共用；同一数据目录只能运行一个实例。
- 创建开始菜单入口，桌面快捷方式可选。
- 升级前关闭软件，重新运行新版安装包即可。安装器检测占用文件时询问关闭相关程序，不配置强制结束。
- 默认不自动启动程序，避免意外与已经运行的绿色版争用数据。
- 卸载只删除安装器登记的程序文件与快捷方式，不删除索引、缓存、设置、登录凭据或图库。
- 首次安装选择图库之外的新建或空目录；拒绝覆盖已有普通文件的目录，并阻止数据目录、常见图片/视频目录、NAS 共享和符号链接路径。命令行 /DIR 执行同样检查。
- 覆盖升级自动沿用上次安装路径；若已有安装并需换盘，先卸载再选择新目录安装，应用数据保持原位置。
- 此脚本不提供自动更新，也不发布 GitHub 或更新 NAS。

## 构建

准备 Inno Setup 6.3 或以上的 6.x 编译器。构建脚本不会自动下载或安装它。

在源码目录执行：

```powershell
.\.venv\Scripts\python.exe scripts/verify_bundle.py --tag final
.\.venv\Scripts\python.exe scripts/package_release.py --output-dir ..\release
.\.venv\Scripts\python.exe scripts/build_installer.py --check-only
.\.venv\Scripts\python.exe scripts/build_installer.py
```

默认查找 PATH、当前用户和 Program Files 下的 Inno Setup 6；其他位置使用 `--iscc "完整路径\ISCC.exe"`。

手机访问预览版使用同一安装器身份，可覆盖原镜迹安装并保留应用数据。为区分公开 0.1.8，发布文件命名为 `LensAtlas-0.1.8-mobile-access-preview-Setup-x64.exe`；安装器内部版本沿用 0.1.8，不宣称正式新版本已发布。可用 `--portable` 指定预览 ZIP，`--evidence` 指定与其中 EXE 校验值一致的桌面验证记录。隔离验证加上 `verify_installer.py --mobile-share` 会检查安装后的手机查询与扫描接口。

安装包从已验证、校验值匹配的绿色版 ZIP 提取到临时目录后编译，不打包开发目录、真实图库或运行时数据。编译失败保留原有发布文件。成功时生成安装 EXE、SHA-256 和构建记录。构建记录不会把编译成功等同于实际安装验证通过。

## 隔离验证

```powershell
.\.venv\Scripts\python.exe scripts/build_installer.py --qa
.\.venv\Scripts\python.exe scripts/verify_installer.py
.\.venv\Scripts\python.exe scripts/audit_release.py
```

QA 安装包使用独立 AppId、程序目录和快捷方式名，且不自动启动。验证脚本要求测试目录原本不存在，依次测试含中文和空格的自选路径安装、不指定 /DIR 的同版本覆盖安装、桌面启动和卸载；所有应用启动均显式传入合成测试数据目录。测试用户自行创建的文件和合成图库在卸载后仍存在。QA 包只留在 `.runtime`，不放进正式 release。

覆盖安装验证不能替代未来每次数据库迁移的兼容性测试。本版安装 EXE 未做发布者代码签名，Windows 可能显示未知发布者提示。

