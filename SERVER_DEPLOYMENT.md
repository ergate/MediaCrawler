# Windows 服务器部署说明

## 版本信息

- 基础源码：MediaCrawler 提交 `0625e01a6bc717a3fc9c96d3dac7fb8957043838`。
- 原服务器定制源码：`MediaCrawler_source.tgz`。
- 本目录是独立的部署源码目录，不包含 `.git`。

## 已合入的服务器定制

- 保留基础提交中的 API 和命令行采集数量限制。
- 保留基础提交中的静态代理支持。
- 本地 CDP 探测使用 `127.0.0.1`，并设置 `trust_env=False`，防止系统中的
  `HTTP_PROXY`、`HTTPS_PROXY` 和 `ALL_PROXY` 拦截 `9222` 端口的本地请求。
- Chrome 远程调试服务仅监听 `127.0.0.1`。
- 抖音、小红书和快手均使用 `domcontentloaded` 页面加载策略。
- 小红书签名同时兼容新旧版本的 `xhshow` 请求载荷签名接口。
- 快手在 `httpx` 请求失败时可以回退到已认证的浏览器会话，同时保留小批量采集限制，
  支持按创作者作品发布时间过滤，并保存能够获取到的评论数。
- 按照基础提交的规则继续对用户标识和个人资料进行匿名化处理。没有合入旧定制中恢复
  原始用户信息的代码。

## 替换服务器源码

替换 MediaCrawler 文件前，先停止工作台采集服务。保留旧目录作为回滚备份，不要把旧目录
中的 `.venv` 或源码文件覆盖到此版本。

```powershell
cd C:\app
Rename-Item MediaCrawler MediaCrawler_backup
Rename-Item MediaCrawler_server_0625e01 MediaCrawler
cd C:\app\MediaCrawler

py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

只有在新旧版本使用同一个 Windows 用户运行，并且确认原浏览器配置正常时，才复制已有的
`browser_data` 目录：

```powershell
Copy-Item -Recurse `
  C:\app\MediaCrawler_backup\browser_data `
  C:\app\MediaCrawler\browser_data
```

否则，应让新版本创建各平台的新浏览器配置目录，并分别完成一次登录。

## 工作台配置

在 `C:\app\social_engagement_dashboard\.env.local` 或工作台的平台连接配置中设置：

```text
MEDIACRAWLER_ROOT=C:\app\MediaCrawler
MEDIACRAWLER_PYTHON=C:\app\MediaCrawler\.venv\Scripts\python.exe
MEDIACRAWLER_NODE_BIN=C:\nvm4w\nodejs\node.exe
MEDIACRAWLER_LOGIN_TYPE=qrcode
MEDIACRAWLER_HEADLESS=false
MEDIACRAWLER_MAX_NOTES=5
MEDIACRAWLER_DY_EVALUATE_RETRIES=8
MEDIACRAWLER_DY_EVALUATE_RETRY_DELAY=1
MEDIACRAWLER_DY_MANUAL_VERIFY_TIMEOUT=180000
MEDIACRAWLER_KS_REQUEST_TIMEOUT=30
MEDIACRAWLER_KS_COMMENT_COUNT_FALLBACK=true
NO_PROXY=127.0.0.1,localhost,::1
```

工作台启动 MediaCrawler 时，会将 `C:\app\MediaCrawler` 设置为子进程的工作目录。因此，
各平台的登录状态会从以下目录读取：

```text
C:\app\MediaCrawler\browser_data\cdp_dy_user_data_dir
C:\app\MediaCrawler\browser_data\cdp_xhs_user_data_dir
C:\app\MediaCrawler\browser_data\cdp_ks_user_data_dir
```

`SAVE_LOGIN_STATE=True` 会持久保存各平台的浏览器配置。`AUTO_CLOSE_BROWSER=True` 会在命令
执行结束后关闭 Chrome，但不会删除浏览器配置或 Cookie。

## 登录状态验证

请在可交互的 RDP 会话中分别执行以下命令。在弹出的 Chrome 窗口中完成扫码登录，然后让
命令正常运行结束：

```powershell
cd C:\app\MediaCrawler

.\.venv\Scripts\python.exe main.py --platform dy --lt qrcode --type search --keywords "测试" --headless false --get_comment false --get_sub_comment false --crawler_max_notes_count 1
.\.venv\Scripts\python.exe main.py --platform xhs --lt qrcode --type search --keywords "测试" --headless false --get_comment false --get_sub_comment false --crawler_max_notes_count 1
.\.venv\Scripts\python.exe main.py --platform ks --lt qrcode --type search --keywords "测试" --headless false --get_comment false --get_sub_comment false --crawler_max_notes_count 1
```

不经过代理检查 CDP：

```powershell
Invoke-RestMethod -NoProxy http://127.0.0.1:9222/json/version
```

只有在 MediaCrawler 管理的浏览器正在运行时，`9222` 端口才会存在。命令结束后该端口关闭
属于正常现象。

最后重启工作台采集服务并检查健康状态：

```powershell
Invoke-RestMethod http://127.0.0.1:8765/api/health
```

扩大采集批次前，应先为每个平台各运行一个账号进行验证。
