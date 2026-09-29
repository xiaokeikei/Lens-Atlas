# Docker 在线与离线交付

从 0.1.2 起，默认服务端口为 **52032**，界面显示 `power by xiaokei`。
两个安装包使用相同后台和界面。运行镜像均包含 Python、后端依赖、ExifTool、FFmpeg/FFprobe、前端静态资源；运行时无需另行安装这些依赖。
主机仍须安装 Docker Engine 和 Compose。离线包不包含 NAS 操作系统或 Docker 引擎。

## 在线安装包

`LensAtlas-版本-docker-online.zip` 包含应用源码和构建配置，不附带 node_modules、Python 虚拟环境或镜像层。
首次构建需要网络下载官方基础镜像、系统工具和软件依赖，完成后可离线运行。

1. 解压，复制 `.env.example` 为 `.env`，填写现有的素材路径、独立应用数据路径、局域网地址及实际 UID/GID。
2. 在包含 compose.yaml 的目录运行：

```sh
docker compose config
docker compose build
docker compose up -d
docker compose ps
```

未来如果维护者已将镜像发布到镜像仓库，可在 `.env` 设置 `LENS_IMAGE=实际仓库地址:明确版本`，使用随包提供的拉取配置：

```sh
docker compose -f compose.registry.yaml pull
docker compose -f compose.registry.yaml up -d
```

拉取配置只需要小型配置文件，但下载到 NAS 的运行镜像仍包含完整依赖。**GitHub 仓库当前提供源码；尚未发布公共容器镜像，没有可以假定存在的公共镜像地址。**

## 离线完整镜像包（linux/amd64）

`LensAtlas-版本-docker-offline-amd64.zip` 包含完整的 Docker image save 镜像归档及运行配置。
支持在无外网环境导入镜像；无需联网构建或下载安装应用依赖。

1. 解压后校验随包校验值：

```sh
sha256sum -c lens-atlas-image.tar.gz.sha256
docker load -i lens-atlas-image.tar.gz
```

2. 复制 `.env.example` 为 `.env`，填写本机实际配置。不要把应用数据目录设成原片目录或原片的子目录。
3. 启动：

```sh
docker compose config
docker compose up -d --no-build --pull never
docker compose ps
```

离线 Compose 不含 build，并使用 pull_policy: never。访问 NAS 局域网地址的 52032 端口。
首次从应用数据目录读取 setup-code.txt，创建管理员后登录。原片挂载只读，配置/数据库/缓存持久化到单独的 /data。

## 升级与旧端口

0.1.1 默认端口为 8765，0.1.2 改为 52032；已有 .env 不会自动改写，升级时显式修改 `LENS_PORT=52032`。
客户端已保存的 NAS 连接地址也应更新。管理员密码、图库及缓存使用原来的应用数据目录，禁止因升级而初始化或覆盖该目录。
停止容器前先记录正在运行的扫描并创建备份；恢复后检查索引，再在任务页恢复因重启暂停的任务。
只使用 docker image save 导出镜像，不使用 docker commit 打包个人运行中的容器。

## 维护者生成交付包

```sh
docker build -t lens-atlas:0.1.5 .
docker image save lens-atlas:0.1.5 | gzip > lens-atlas-0.1.5-image.tar.gz
python scripts/package_docker_release.py --image-archive lens-atlas-0.1.5-image.tar.gz
```

脚本仅收集白名单源码，生成在线和离线 ZIP、SHA-256 校验值；检查镜像版本、平台、默认端口及镜像层中是否混入个人应用数据。
不要提交或上传 `.runtime`、`.env`、原片、缓存、SQLite 数据库、凭据或维护日志。
公开发布前仍须准备第三方许可证和对应源码材料，见 THIRD_PARTY_NOTICES.md；打包不等同于已经完成公开发布。
