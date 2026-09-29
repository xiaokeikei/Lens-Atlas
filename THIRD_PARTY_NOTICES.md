# 第三方软件与分发

应用自身源码使用 MIT，第三方组件不因此重新许可。生成包内的 `licenses/manifest.json`
记录本次构建依赖版本和上游地址；`vendor/manifest.json` 记录外部工具来源及校验值。

| 组件 | 许可证与处理 |
| --- | --- |
| React / FastAPI / Uvicorn / HTTPX | MIT，保留版权及许可证 |
| ECharts / ZRender | Apache-2.0 / BSD，保留包内 LICENSE / NOTICE |
| Pillow | HPND 及随附组件许可证 |
| Python | PSF，随包保留许可证 |
| PySide6 / Shiboken / Qt 基础模块 | 使用开源 LGPLv3 分发选项，不使用商业许可证授权 |
| Qt WebEngine / Chromium | Qt 开源条款及 Chromium 第三方条款；保留 Qt 许可证和第三方清单 |
| Qt Multimedia / Qt 自带 FFmpeg 运行库 | 0.1.1 的原生播放器使用此组件；遵守 Qt 开源条款和其 FFmpeg/第三方许可，不能与另外随包的 BtbN FFmpeg 8.1 构建混为一谈 |
| ExifTool | 作者提供的 Perl 双许可；Windows 包同时包含启动器、Perl 及组件，保留原始包的 LICENSE 和 Licenses_Strawberry_Perl.zip |
| FFmpeg / FFprobe | 本次选用 BtbN **LGPL shared** 构建，未启用 GPL 或 nonfree；随包保留构建原始 LICENSE，版本以工具输出和 manifest 为准 |

Qt 使用目录分发，不把 Qt DLL 静态链接入应用。用户可以替换 `_internal/PySide6` 中 ABI
兼容的共享库；应用不限制为调试修改库所需的逆向工程。Python/应用构建脚本随项目提供。
FFmpeg 是独立子进程；共享库在 `_internal/vendor`，允许 ABI 兼容替换。

上游源码及构建入口：

- Qt / Qt for Python：`https://download.qt.io/official_releases/qt/`、`https://download.qt.io/official_releases/QtForPython/pyside6/`
- Qt WebEngine 的许可说明与 Chromium 许可入口：`https://doc.qt.io/qt-6/qtwebengine-licensing.html`
- ExifTool：`https://exiftool.org/`、`https://github.com/exiftool/exiftool`
- Windows ExifTool 启动器：`https://oliverbetz.de/pages/Artikel/ExifTool-for-Windows`
- FFmpeg：`https://github.com/FFmpeg/FFmpeg`；对应构建脚本 `https://github.com/BtbN/FFmpeg-Builds`

当前 GitHub 仓库公开项目源码，现有本机验收用二进制构建尚未通过本仓库 Release 分发。正式面向公众分发二进制前，
维护者需要为**确切构建版本**准备 LGPL 所要求的对应源码获取方式，核对 Qt WebEngine
及 FFmpeg 所有嵌入第三方依赖的通知，并留存源码、构建材料和二进制校验值。
仅附上许可证清单并不等于完成所有公开分发义务。

Docker 使用 Debian 提供的 ExifTool / FFmpeg 包，许可证和来源记录位于容器的
`/usr/share/doc`。其编译选项和许可证不应与 Windows 的 LGPL shared 构建混同。
