# 打包说明

## 流程

1. 安装依赖并拉取 Chromium：`build.py` 内自动执行
2. 暂存 `_bundle/ms-playwright`（嵌入式浏览器）
3. 暂存 `_bundle/node/node.exe`（抖音 `a_bogus` 签名，用户无需安装 Node）
4. PyInstaller 单文件 exe → `dist/SocialMediaTool.exe`
5. 打 zip + 生成 `README.txt` → `release/SocialMediaTool.zip`

## dist 与 release

- **dist/**：PyInstaller 默认输出，方便开发者本机双击测试
- **release/**：对外交付物（zip 内含 exe 与使用说明）

不要合并为一个目录；两者职责不同，详见根目录 [README.md](../README.md)。

## 环境要求（仅打包机）

- Windows
- Python 3.10+
- 网络（首次需下载 Node 便携包、复制本机 Playwright Chromium）

最终用户 **不需要** 安装 Python、Node、Playwright。

## 首次运行 exe

单文件 exe 启动时会解压内嵌资源，约 10–20 秒。若杀毒软件拦截，请将程序加入白名单（内嵌 Chromium）。

## 开发机浏览器

`install_browsers.bat` 仅用于 `python main.py` 开发调试；exe 用户不需要执行。
