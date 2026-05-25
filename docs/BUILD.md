# 打包说明

## Windows 流程

1. 安装依赖并拉取 Chromium：`build.py` 内自动执行
2. 暂存 `_bundle/ms-playwright`（嵌入式浏览器）
3. 暂存 `_bundle/node/node.exe`（抖音 `a_bogus` 签名，用户无需安装 Node）
4. PyInstaller 单文件 exe → `dist/SocialMediaTool.exe`
5. 打 zip + 生成 `README.txt` → `release/SocialMediaTool.zip`

## Mac（Apple Silicon）流程

1. 在 **macOS** 或 GitHub Actions `macos-14` 上执行 `python build_mac.py`
2. 暂存 `_bundle/ms-playwright`（darwin-arm64 Chromium）
3. 暂存 `_bundle/node/node`（darwin-arm64 Node）
4. PyInstaller 输出 `.app` → `dist/SocialMediaTool.app`
5. 打 zip + 生成 `README-mac.txt` → `release/SocialMediaTool-mac-arm64.zip`

CI 构建：push 到 `master` 会自动触发 Mac 打包；也可在 GitHub **Actions** 页手动运行 **Build macOS arm64**，或 push `v*` 标签时触发。产物在 workflow artifact 中下载。

**首次使用前**需在仓库 **Settings → Actions → General** 开启 Actions，并选择 **Allow all actions and reusable workflows**，保存后 workflow 才会出现在左侧列表。

设置环境变量 `CODESIGN_APP=1` 时，`build_mac.py` 会对 `.app` 做 ad-hoc 签名（CI 默认开启），减轻 Gatekeeper 拦截。

**不能在 Windows 上交叉编译 Mac 包。**

## dist 与 release

- **dist/**：PyInstaller 默认输出，方便开发者本机双击测试
- **release/**：对外交付物（zip 内含 exe/.app 与使用说明）

不要合并为一个目录；两者职责不同，详见根目录 [README.md](../README.md)。

## 环境要求（仅打包机）

### Windows

- Windows
- Python 3.10+
- 网络（首次需下载 Node 便携包、复制本机 Playwright Chromium）

### Mac

- macOS 14+（Apple Silicon 推荐）
- Python 3.10+
- 网络（首次需下载 Node 便携包、复制本机 Playwright Chromium）

最终用户 **不需要** 安装 Python、Node、Playwright。

## 首次运行

### Windows exe

单文件 exe 启动时会解压内嵌资源，约 10–20 秒。若杀毒软件拦截，请将程序加入白名单（内嵌 Chromium）。

### Mac .app

1. 解压 `SocialMediaTool-mac-arm64.zip`，得到 `SocialMediaTool.app`
2. 首次启动约 10–20 秒（解压内嵌 Chromium / Node）
3. 若提示「无法验证开发者」或「已损坏」：
   - **推荐**：Finder 中右键 `.app` → **打开** → 再点 **打开**
   - 或终端执行：`xattr -cr SocialMediaTool.app`
4. 用户数据目录：`~/Library/Application Support/SocialMediaTool`
5. 开发者 bypass：与 `.app` **同级** 放置 `key.txt`，内容为 `meyou`（与 Windows exe 同级规则一致）

## 开发机浏览器

`install_browsers.bat` 仅用于 `python main.py` 开发调试；打包用户不需要执行。
