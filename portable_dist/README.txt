# Flask 便携版 - Win7 离线运行包

## 使用方法

1. 将此目录拷贝到 Win7 系统的任意位置
2. 双击 start.bat
3. 浏览器访问 http://127.0.0.1:5000

## 技术说明

- 嵌入式 Python: 3.8.10 (amd64)
- Flask: 2.3.3 + Werkzeug: 2.3.7
- 已内置 sitecustomize.py 修复 zipimport 问题
- 已打包 VC++ 运行库 DLL
- 无需安装任何软件，绿色便携

## 目录结构

```
portable_dist/
├── start.bat              # 启动脚本
├── app/                    # Flask 应用代码
│   ├── fix_flask_env.py
│   └── ...
└── python/                 # 嵌入式 Python
    ├── python.exe
    ├── python38.dll
    ├── python38.zip
    ├── *.pyd               # C 扩展模块
    ├── *.dll               # VC++ 运行库
    └── Lib/
        └── site-packages/  # Flask 等第三方包
