# Social Media Collector（biya）

多平台社媒链接采集桌面工具（CustomTkinter + Playwright），支持登录账号、批量采集互动数据并导出 Excel。

## 快速开始（开发）

```bash
pip install -r requirements.txt
python -m playwright install chromium   # 或双击 install_browsers.bat
python main.py
```

## 打包 exe（Windows）

```bash
build.bat
# 或
python build.py
```

打包说明见 [docs/BUILD.md](docs/BUILD.md)。

## 目录结构

| 目录 | 说明 |
|------|------|
| `main.py` | 应用入口 |
| `config.py` | 全局配置、平台列表 |
| `core/` | 数据模型、导出 schema |
| `infra/` | 浏览器、数据库、各平台采集器 |
| `services/` | 登录、批量采集业务 |
| `ui/` | 界面 |
| `shared/` | UI 与 asyncio 桥接 |
| `hooks/` | PyInstaller 运行时 hook |

## 构建产物（勿与源码混淆）

| 目录 | 生成方式 | 用途 |
|------|----------|------|
| `_bundle/` | `build.py` 暂存 | 打包前嵌入的 Chromium、Node |
| `build/` | PyInstaller | 中间文件，可删 |
| `dist/` | PyInstaller | **本地测试用** 单文件 exe |
| `release/` | `build.py` | **发给用户** 的 zip（exe + README） |

- **本地验证**：运行 `dist/SocialMediaTool.exe`
- **对外发布**：发送 `release/SocialMediaTool.zip`

上述 `build/`、`dist/`、`_bundle/` 可随时整目录删除以释放磁盘；下次执行 `build.py` 会重新生成。`release/` 在每次打包时会自动清空旧 zip 与说明文件。

## 用户数据路径

账号与导出文件保存在：`%APPDATA%\SocialMediaTool`
