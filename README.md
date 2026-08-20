# ustc-iwan-docker

一个面向 Docker 部署的 **非官方** USTC iWAN SOCKS5 wrapper。

本仓库不修改 `ustc-iwan` 的 Rust 代码，而是围绕上游 Release 提供容器启动、凭据持久化、健康检查、自动重连和 GHCR 构建流程。运行时使用上游原生的无 TUN SOCKS5 模式，因此正常部署不需要 `privileged`、`CAP_NET_ADMIN` 或 `/dev/net/tun`。

> [!IMPORTANT]
> 本项目不是中国科学技术大学、Panabit 或上游 `ustc-iwan` 项目的官方发行物。请仅在你有权访问的 USTC/iWAN 网络与服务中使用。

## 上游与致谢

核心 iWAN/OIDC/SOCKS5 实现来自：

- [`yyy1mu/ustc-iwan`](https://github.com/yyy1mu/ustc-iwan)

感谢 `yyy1mu` 以及该项目的所有贡献者完成 USTC iWAN 协议、统一身份认证和用户态 SOCKS5 支持。本仓库只负责 Docker 包装和部署自动化，不重新实现这些核心功能。

也感谢 [`TioeAre/ustc_iwan_docker`](https://github.com/TioeAre/ustc_iwan_docker) 对 Docker 化、代理暴露与长期运行场景的探索；本仓库采用的是上游后来加入的原生 non-TUN SOCKS5 路径，因此架构有所不同。

## 为什么使用原生 SOCKS5

数据路径为：

```text
应用 / 其他容器
      │
      │ socks5h://...
      ▼
ustc-iwan-docker :1080
      │
      ▼
上游 iwan-client-oidc --socks
      │
      ▼
USTC iWAN
      │
      ▼
USTC 内网 TCP 服务
```

这意味着只有显式使用 SOCKS5 代理的连接会进入 iWAN；宿主机和其他容器的默认路由不会被修改。

当前上游 SOCKS5 的主要限制也会继承到本镜像：仅 TCP/IPv4 `CONNECT`，不支持 SOCKS5 UDP ASSOCIATE、IPv6 或纯 UDP 服务。域名请求应优先使用 `socks5h://`，让 hostname 交给代理端解析。

## 关于上游二进制与许可证

本仓库自己的 Dockerfile、shell 脚本、Compose 配置和 GitHub Actions 工作流采用 **MIT License**，见 [`LICENSE`](LICENSE)。

`yyy1mu/ustc-iwan` 是独立上游项目，其代码和 Release 产物不因本仓库采用 MIT 而自动获得 MIT 授权。由于上游当前没有在仓库根目录声明明确的软件许可证，本仓库的公共 GHCR 镜像 **不直接内置或重新分发上游二进制**。

容器第一次启动（以及上游版本变化后）会直接从 `yyy1mu/ustc-iwan` 的 GitHub Releases 下载所选版本到持久化 volume。若 `UPSTREAM_SHA256S` 中已经记录对应 Release asset 的 SHA-256，启动脚本还会校验下载内容。这样可以明确区分本仓库的 MIT wrapper 与上游软件本身。

## 当前上游版本

版本由 [`UPSTREAM_VERSION`](UPSTREAM_VERSION) 锁定。初始版本为 `v2.2.0`。

GitHub Actions 大约每 5 天检查一次 `yyy1mu/ustc-iwan` 的 **latest stable Release**（忽略 draft/prerelease）。发现新版本后不会直接升级生产镜像，而是：

```text
发现新 stable Release
        ↓
校验 amd64 / arm64 Release assets
        ↓
计算 SHA-256
        ↓
自动创建更新 PR
        ↓
人工 review / merge
        ↓
构建 multi-arch GHCR 镜像
        ↓
发布 vX.Y.Z 与 stable tags
```

> GitHub Actions 的 `day-of-month` cron 不是严格的 120 小时间隔；这里使用低频的 `*/5` 调度，因此通常约每 5 天运行一次，在跨月边界可能有少量偏差。

## 快速开始

### 1. 拉取镜像

建议生产环境固定版本 tag，而不是直接追 `stable`：

```bash
docker pull ghcr.io/develata/ustc-iwan-docker:v2.2.0
```

也可以直接使用仓库中的 `compose.yaml`：

```bash
cp .env.example .env
docker compose pull
```

### 2. 第一次获取 USTC iWAN 配置

```bash
docker compose run --rm iwan fetch
```

按照终端提示完成 USTC 统一身份认证，并将要求的回调 URL 粘贴回终端。配置会写到：

```text
./data/iwan/servers.json
```

该文件包含敏感认证/线路信息，已被 `.gitignore` 排除；不要提交到 Git。

查看已获取线路：

```bash
docker compose run --rm iwan list
```

然后在 `.env` 中设置想使用的线路序号，例如：

```dotenv
IWAN_SERVER_INDEX=1
```

### 3. 启动长期代理

```bash
docker compose up -d
```

默认只向宿主机 loopback 暴露：

```text
socks5h://127.0.0.1:1080
```

测试：

```bash
curl --proxy socks5h://127.0.0.1:1080 https://api.llm.ustc.edu.cn/
```

请注意 `socks5h://` 与 `socks5://` 的区别：前者将域名交给 SOCKS server 处理，在宿主机开启 Mihomo/Clash fake-ip 时尤其重要。

## 给其他 Docker 容器使用

Compose 会创建名为 `ustc-iwan-proxy` 的 Docker network。其他 Compose 项目可以加入该 external network：

```yaml
services:
  app:
    image: your-image
    networks:
      - ustc-iwan-proxy

networks:
  ustc-iwan-proxy:
    external: true
```

然后应用使用：

```text
socks5h://ustc-iwan:1080
```

如果应用支持按请求/按目标配置代理，建议只让确实需要 USTC 内网访问的连接使用该端口，而不是把整个容器的默认网络都送入 iWAN。

## Mihomo / Clash TUN 注意事项

如果宿主机同时运行 Mihomo/Clash TUN：

1. USTC 相关域名最好从 fake-ip 中排除，避免客户端在本地先得到 `198.18.0.0/16` 一类 fake IP。
2. 使用 SOCKS 时优先写 `socks5h://`。
3. 确保容器到实际 iWAN server 的 UDP 连接不要被不必要地再次套入其他代理。
4. 上游 SOCKS 当前会自行做 IPv4 DNS 查询；如果宿主机 TUN 对 Docker 的 DNS/UDP 流量有特殊劫持规则，需要相应做 bypass。

## 健康检查与自动重连

容器内 wrapper 会对 SOCKS 数据面做周期性 HTTP 请求。默认检测：

```text
https://api.llm.ustc.edu.cn/
```

HTTP 状态码本身不作为失败条件；只要 DNS、SOCKS、TCP/TLS 和响应传输能够完成，就视为数据面可用。连续失败达到阈值后，wrapper 会终止 iWAN 子进程，由 Docker 的 `restart: unless-stopped` 重建容器会话。

相关环境变量见 [`.env.example`](.env.example)。

## 手动构建

开发或排错时仍可本地构建 wrapper 镜像：

```bash
docker build \
  --build-arg IWAN_VERSION="$(cat UPSTREAM_VERSION)" \
  -t ustc-iwan-docker:local .
```

注意：这个构建过程不会把上游 `iwan-client-oidc` 放进镜像；它会在容器首次运行时从上游 Release 下载。

## Release 更新策略

- 只跟踪 GitHub **stable Release**，不跟踪 `main`。
- 自动检查只创建 PR，不自动 merge。
- 合并更新 PR 后才会重新发布 GHCR。
- 发布 `ghcr.io/develata/ustc-iwan-docker:vX.Y.Z`。
- 同时更新 `ghcr.io/develata/ustc-iwan-docker:stable`。
- 生产部署建议固定 `vX.Y.Z`，需要升级时手动修改 tag。

## License

本仓库的原创 wrapper 内容采用 [MIT License](LICENSE)。上游 `yyy1mu/ustc-iwan` 及其 Release 产物不属于本仓库 MIT 授权范围，相关权利归上游作者/权利人所有。
