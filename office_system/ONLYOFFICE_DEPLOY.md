# ONLYOFFICE Docs 部署说明

本项目只在 Flask 端集成 ONLYOFFICE。PythonAnywhere Web App 中不要安装或运行 Document Server；请在另一台可运行 Docker、具有公网 HTTPS 地址的服务器部署 ONLYOFFICE Docs Community Edition。

## PythonAnywhere 端

1. 在虚拟环境安装依赖：`pip install -r requirements.txt`。
2. 在 PythonAnywhere Web 配置或 WSGI 启动前设置下列环境变量（目录中的 `<YOUR_USERNAME>` 必须替换，不要照抄占位符）：

```bash
ONLYOFFICE_ENABLED=true
ONLYOFFICE_SERVER_URL=https://docs.example.com
ONLYOFFICE_JWT_ENABLED=true
ONLYOFFICE_JWT_SECRET=<LONG_RANDOM_SHARED_SECRET>
APP_PUBLIC_URL=https://castlej.pythonanywhere.com
DOCUMENT_STORAGE_FOLDER=/home/<YOUR_USERNAME>/26creativity/office_system/data/online_documents
DOCUMENT_VERSION_FOLDER=/home/<YOUR_USERNAME>/26creativity/office_system/data/document_versions
DOCUMENT_MAX_UPLOAD_MB=51200
DOCUMENT_URL_TOKEN_MAX_AGE=600
ONLYOFFICE_DOWNLOAD_HOSTS=docs.example.com
```

3. 创建两个存储目录，并授予 Web App 用户读写权限。不要将目录或文件提交到 Git。
4. 在 `office_system` 下运行 `python migrate.py`。迁移幂等，只新增字段和索引。
5. Reload Web App，管理员登录后访问 `/docs/onlyoffice/status`。
6. 用有效的短时 token 检查 `/docs/<id>/content?token=...`，并在 Document Server 日志中确认其能访问内容 URL 和 `/docs/<id>/callback`。`APP_PUBLIC_URL` 必须是外部服务可访问的 HTTPS 根地址。

## ONLYOFFICE 服务器端

下面只是结构示例。生产镜像应替换为已在预发布环境验证的固定版本号，不能无条件使用 `latest`，密钥也不能写入仓库。

```yaml
services:
  onlyoffice:
    image: onlyoffice/documentserver:<TESTED_VERSION>
    restart: unless-stopped
    environment:
      JWT_ENABLED: "true"
      JWT_SECRET: "${ONLYOFFICE_JWT_SECRET}"
    ports:
      - "127.0.0.1:8080:80"
    volumes:
      - onlyoffice_data:/var/www/onlyoffice/Data
      - onlyoffice_logs:/var/log/onlyoffice
volumes:
  onlyoffice_data:
  onlyoffice_logs:
```

由 Nginx 提供 HTTPS 并反向代理到 `127.0.0.1:8080`。必须转发 `Host`、`X-Forwarded-Proto`、真实客户端地址，并正确代理 WebSocket 的 `Upgrade`/`Connection` 头；上传大小和超时应大于 Flask 端限制。防火墙需允许浏览器访问 Document Server，并允许 Document Server 通过 HTTPS 访问：

```text
https://castlej.pythonanywhere.com/docs/<id>/content
https://castlej.pythonanywhere.com/docs/<id>/callback
```

双方 JWT secret 必须完全一致，生产环境强烈建议始终启用 JWT。Document Server 回调返回的下载地址主机必须加入 `ONLYOFFICE_DOWNLOAD_HOSTS`，只填主机名，不含协议和路径。

中文字体可复制到容器的 `/usr/share/fonts/truetype/custom/`（或挂载到该目录），然后在容器内运行 `fc-cache -fv`，再执行 Document Server 提供的字体生成脚本并重启容器。升级镜像后需确认字体仍存在。

健康检查：浏览器和 Flask 主机访问 `https://docs.example.com/healthcheck` 应返回 `true`；管理员状态接口应显示服务可达、存储可写。随后新建测试文档，编辑保存、关闭重开、下载并恢复历史版本。若使用代理/WAF，额外验证 WebSocket 和较大文件回调没有被拦截。

## 安全提示

不要记录或回显 JWT secret。定期轮换密钥时必须同步两端并安排维护窗口。内容 token 有效期由 `DOCUMENT_URL_TOKEN_MAX_AGE` 控制；回调还受用途绑定 token、JWT 和下载主机白名单共同保护。
