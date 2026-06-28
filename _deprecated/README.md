# _deprecated 文件夹说明

此文件夹存放从项目主目录中剔除的**无用文件和代码**，保留以供回退和人工审核。

## 清理内容

### 1. `static/kindeditor/`
- **asp/**, **asp.net/**, **jsp/** — 其它后台上传示例（本项目是 Python/Flask 栈，不需要）
- **docs/** — 文档（产品部署不需要）
- **lib/firebug-lite/** — 浏览器调试工具（非生产需要）
- **Gruntfile.js**, **package.json** — 构建/包管理文件
- **changelog.txt**, **.gitignore** — 非运行需要的文件

### 2. `static/x-spreadsheet/`
- **src/**, **build/**, **test/**, **docs/** — 源码/构建/测试/文档（保留 `dist/` 即可运行）
- **.github/**, **.babelrc**, **.eslintignore**, **.eslintrc.js**, **.travis.yml**, **.gitignore** — 开发配置
- **package.json**, **package-lock.json**, **readme.md**, **LICENSE**, **CODE_OF_CONDUCT.md** — 元数据
- **index.html**, **assets/** — 演示页面

### 3. `static/icon-review.html`
图标检查测试页面，未被任何模板引用。

### 4. `app/queries.py`
查询辅助函数模块，未被任何视图/蓝图导入。各视图已内置等价查询。保留此文件供参考。

### 5. `static/uploads/` 
旧的任务附件上传目录（位于 `app/static/uploads/` 下），实际上传应使用 `data/uploads/`。

---

**清理日期**: 2026-06-09
**清理后验证**: 系统可正常启动，所有功能不受影响
