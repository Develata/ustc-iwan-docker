# ustc-iwan-docker

一个面向 Docker 部署的 **非官方** USTC iWAN SOCKS5 wrapper。

本仓库不修改 `ustc-iwan` 的 Rust 代码，只负责 Docker 启动、凭据持久化、健康检查、自动重连和 GHCR 发布。运行时使用上游原生的 non-TUN SOCKS5 模式，因此正常部署不需要 `privileged`、`CAP_NET_ADMIN` 或 `/dev/net/tun`。

> [!IMPORTANT]
> 本项目不是中国科学技术大学、Panabit 或上游 `ustc-iwan` 项目的官方发行物。请仅在你有权访问的 USTC/iWAN 网络与服务中使用。

## AI 生成声明

> [!NOTE]
> **除引用和调用的上游项目/Release 产物外，本仓库的原创内容完全由 AI 自主构造。**
>
> 本仓库中的 Docker 架构、`Dockerfile`、`entrypoint.sh`、Compose 配置、GitHub Actions 工作流、Release 跟踪机制、健康检查与自动重连逻辑、文档，以及后续调试修复，均由 **OpenAI ChatGPT** 根据仓库所有者给出的目标、约束和授权，自主完成设计、实现、修改并直接写入 GitHub 仓库。
>
> 仓库所有者负责创建 GitHub repository、提出需求和作出高层方案选择，但未手工编写本仓库上述实现内容。因此，本仓库应被视为 **AI-generated / AI-maintained software**；使用者应像审查其他自动生成代码一样，自行审查其正确性、安全性和适用性。
>
> 此声明**不适用于**上游 [`yyy1mu/ustc-iwan`](https://github.com/yyy1mu/ustc-iwan) 的源码或 Release 产物。本仓库不声称这些上游内容由 AI 生成，也不改变其作者、贡献者或权利归属。

## 上游与致谢

核心 iWAN / OIDC / SOCKS5 实现来自：

- [`yyy1mu/ustc-iwan`](https://github.com/yyy1mu/ustc-iwan)

感谢 `yyy1mu` 以及该项目的所有贡献者完成 USTC iWAN 协议、统一身份认证和用户态 SOCKS5 支持。本仓库只负责 Docker 包装和部署自动化，不重新实现这些核心功能。

也感谢 [`TioeAre/ustc_iwan_docker`](https://github.com/TioeAre/ustc_iwan_docker) 对 Docker 化、代理暴露和长期运行场景的探索。本仓库采用的是上游后来加入的原生 non-TUN SOCKS5 路径，因此不需要 TUN + 3proxy 架构。

## 架构

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

只有显式使用 SOCKS5 代理的连接会进入 iWAN；宿主机和其他容器的默认路由不会被修改。

当前上游 SOCKS5 的限制也会继承到本镜像：主要面向 TCP/IPv4 `CONNECT`，不提供 SOCKS5 UDP ASSOCIATE、IPv6 或纯 UDP 服务。域名请求建议使用 `socks5h://`，让 hostname 交给代理端解析。

## 镜像与上游 Release

本仓库的 `main` 分支 **不会因为上游发布新版本而被自动修改**。

GitHub Actions 大约每 5 天检查一次 `yyy1mu/ustc-iwan` 的 latest stable Release（忽略 draft/prerelease）：

```text
yyy1mu/ustc-iwan latest stable Release
                 │
                 ▼
      检查 GHCR 是否已有 vX.Y.Z
           │                │
          有               没有
           │                ▼
          结束       下载 amd64/arm64 assets
                            │
                            ▼
                       计算 SHA-256
                            │
                            ▼
                    构建 multi-arch wrapper
                            │
                            ▼
           ghcr.io/develata/ustc-iwan-docker:vX.Y.Z
           ghcr.io/develata/ustc-iwan-docker:stable
```

因此：

- `vX.Y.Z`：对应某个上游 stable Release，发布后不会由普通 `main` 变更覆盖。
- `stable`：当前推荐的滚动 tag。新的上游 stable Release 发布时会更新；本仓库 wrapper 自身更新时也会重建。
- 上游版本号、amd64/arm64 SHA-256 和 wrapper Git revision 都记录在镜像 OCI labels / ENV 中，不写回 `main`。

GitHub cron 的 `*/5` 是按月日历计算，不是严格的 120 小时周期，因此跨月时可能出现少量偏差。

## 许可证边界

本仓库原创的 Dockerfile、shell 脚本、Compose 配置、文档和 GitHub Actions 工作流采用 **MIT License**，见 [`LICENSE`](LICENSE)。

`yyy1mu/ustc-iwan` 是独立上游项目，其代码和 Release 产物不因本仓库采用 MIT 而自动获得 MIT 授权。由于上游当前没有在仓库根目录声明明确的软件许可证，本仓库的公共 GHCR 镜像 **不直接内置或重新分发上游二进制**。

镜像只包含 wrapper。容器第一次启动时，会从对应的 `yyy1mu/ustc-iwan` GitHub Release 下载当前架构的 `iwan-client-oidc` 到持久化 volume，并使用构建镜像时记录的 SHA-256 强制校验。checksum 不匹配时容器会拒绝启动。

## 快速开始

### 1. 拉取镜像

默认跟随 `stable`：

```bash
docker pull ghcr.io/develata/ustc-iwan-docker:stable
```

如果希望固定版本：

```bash
docker pull ghcr.io/develata/ustc-iwan-docker:vX.Y.Z
```

使用仓库中的 Compose：

```bash
cp .env.example .env
docker compose pull
```

`.env.example` 默认：

```dotenv
IWAN_IMAGE_TAG=stable
```

生产环境如果希望完全固定，可以改成：

```dotenv
IWAN_IMAGE_TAG=vX.Y.Z
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

查看线路：

```bash
docker compose run --rm iwan list
```

然后在 `.env` 中设置线路序号，例如：

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

注意 `socks5h://` 与 `socks5://` 的区别：前者把域名交给 SOCKS server 解析，在宿主机开启 Mihomo/Clash fake-ip 时尤其重要。

## 给其他 Docker 容器使用

Compose 会创建名为 `ustc-iwan-proxy` 的 Docker network。其他 Compose 项目可以加入这个 external network：

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

应用使用：

```text
socks5h://ustc-iwan:1080
```

如果应用支持按请求或按目标配置代理，建议只让确实需要 USTC 内网访问的连接使用这个端口，而不是把整个容器默认网络送入 iWAN。

## Mihomo / Clash TUN 注意事项

如果宿主机同时运行 Mihomo/Clash TUN：

1. USTC 相关域名最好从 fake-ip 中排除，避免客户端本地先得到 `198.18.0.0/16` 一类 fake IP。
2. 使用 SOCKS 时优先写 `socks5h://`。
3. 确保容器到实际 iWAN server 的 UDP 连接不要被不必要地再次套入其他代理。
4. 上游 SOCKS 当前会自行做 IPv4 DNS 查询；如果宿主机 TUN 对 Docker DNS/UDP 流量有特殊劫持规则，需要相应做 bypass。

## 健康检查与自动重连

wrapper 会通过 SOCKS 数据面周期性访问：

```text
https://api.llm.ustc.edu.cn/
```

HTTP 状态码本身不作为失败条件；只要 DNS、SOCKS、TCP/TLS 和响应传输可以完成，就视为数据面可用。连续失败达到阈值后，wrapper 会终止 iWAN 子进程，由 Docker 的 `restart: unless-stopped` 重建容器会话。

相关参数见 [`.env.example`](.env.example)。

## GitHub Actions 权限

两个 workflow 均只使用最小权限：

```yaml
permissions:
  contents: read
  packages: write
```

它们不会 push `main`、不会创建 PR、不会 approve/merge PR。因此仓库级 **Workflow permissions 可以保持默认的只读设置**，也无需打开 `Allow GitHub Actions to create and approve pull requests`。

## Wrapper 代码更新与上游 Release 更新的区别

### 上游发布新 stable Release

约每 5 天的 `Publish upstream stable release` workflow 检查一次。如果对应 `vX.Y.Z` 镜像不存在，则发布：

```text
:vX.Y.Z
:stable
```

### 本仓库 `main` 更新

Dockerfile、entrypoint、workflow 等 wrapper 文件发生变化时，`Build stable wrapper image` 会读取当时最新的上游 stable Release，只重建：

```text
:stable
```

已经存在的版本化 `:vX.Y.Z` 不会因此被覆盖。

## 手动触发发布检查

需要立即检查上游而不等待约 5 天时，可以进入 GitHub 仓库的 **Actions → Publish upstream stable release → Run workflow** 手动触发。

## License

本仓库原创 wrapper 内容采用 [MIT License](LICENSE)。上游 `yyy1mu/ustc-iwan` 及其 Release 产物不属于本仓库 MIT 授权范围，相关权利归上游作者/权利人所有。
