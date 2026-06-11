# 问题清单（由 Cursor 修改后产生）

> 生成时间：2026-06-06 | 仅列出问题，不做修改

---

## 🔴 严重问题（会导致运行失败）

### 1. 缺少模板文件
| 问题 | 详情 |
|------|------|
| 缺失文件 | `app/templates/stats/tasks.html` |
| 影响 | stats 蓝图路由可能报 500 错误 |

### 2. 数据库 Schema 不兼容
| 问题 | 详情 |
|------|------|
| 新增字段 | `tabs` 表新增 `tab_type`（默认 `'bulletin'`）、`icon`（默认 `'📁'`）、`url`（默认空） |
| 新增表 | `task_categories`、`bulletin_categories`（models.py 已定义，但旧数据库无此表） |
| 影响 | 旧数据库启动时可能崩溃，需删除 `data/database.db` 重建 |

### 3. 种子数据过时
| 问题 | 详情 |
|------|------|
| 回退 | `database.py` 被恢复到旧版本，使用英文名称（`'Super Admin'`、`'IT'`、`'General'`） |
| 缺失 | 种子数据未设置新字段 `tab_type`、`icon`、`url` |

### 4. 侧边栏数据源不明确
| 问题 | 详情 |
|------|------|
| `base.html` 使用 `visible_tabs` | 需要 context processor 注入（views/__init__.py 中已有 `load_tabs()` 写入 `g.visible_tabs`） |
| `base.html` 使用 `sidebar_tabs` | **未找到注入来源**，base.html 引用了但无对应 context processor |
| 依赖 `g.visible_tabs` | `app.context_processor` 未将 `g.visible_tabs` 传给模板，模板直接用 `visible_tabs` 而不是 `g.visible_tabs` |

---

## 🟠 IE11 兼容性问题（违反项目约束）

### 5. CSS Grid（IE11 不支持）
| 位置 | 数量 |
|------|------|
| `app.css` | 4 处 `display: grid` |
| `index.html` | 1 处（dashboard stats） |
| `bulletin/index.html` | 1 处（columns grid） |

### 6. CSS Flexbox（IE11 部分支持，易出问题）
| 位置 | 数量 |
|------|------|
| `app.css` | **43 处** `display: flex` |

### 7. 其他 IE11 不兼容属性
- `linear-gradient` 在 `index.html` dashboard header 中使用
- `transform`、`transition` 在 app.css 中大量使用

### 8. Emoji 图标
- `base.html` 侧边栏使用 emoji（📋📢📝📁👥🏷📑📂📊⏰📄➕✏🏠）
- IE11 对 emoji 渲染支持差，可能显示为方框

---

## 🟡 功能与逻辑问题

### 9. Flash 消息回退为英文
| 文件 | 问题 |
|------|------|
| `decorators.py` | 登录/权限提示仍为英文（`'Please login first'`、`'Super admin required'`） |
| `database.py` | 默认用户名称为英文 |

### 10. 权限模型变更未完整实现
| 项目 | 详情 |
|------|------|
| 新增 `require_admin` 装饰器 | 允许 `super_admin` + `dept_admin` |
| `admin.py` 已使用 | Tab/栏目管理从 `require_super_admin` 改为 `require_admin` |
| 影响 | 部门管理员现在可以管理Tab和栏目（原设计仅超管可操作） |

### 11. 新增蓝图路由未在菜单中完整体现
| 蓝图 | 现有路由 | 侧边栏是否链接 |
|------|---------|--------------|
| `contacts` | `/contacts` | 否（base.html 无入口） |
| `stats` | `/stats`、`/tasks/stats` | 否 |
| `settings` | `/settings`、`/settings/task-categories`、`/settings/bulletin-categories` | 部分（任务类别、公示分类有入口） |

### 12. CSS 文件膨胀
| 指标 | 值 |
|------|-----|
| 当前行数 | **1369 行** |
| 原先行数 | ~200 行 |
| 问题 | 大量新增样式可能未被使用，需清理 |

---

## 🟢 模板层面的问题

### 13. base.html 结构变化
- Header 完全重写（新增 avatar、header-center、breadcrumb 区域）
- 侧边栏改为 section 分组结构
- Tab bar 操作按钮改为 emoji（🔄✕）
- 移除了「帮助」和「个人设置」的独立菜单项

### 14. index.html 结构变化
- 采用 CSS Grid 布局（`stats-grid`、`dashboard-grid`）
- 新增 `dashboard-header` 带渐变背景
- 卡片样式全部重写

### 15. bulletin/index.html 结构变化
- 采用 CSS Grid 列布局（`columns-grid`）
- 新增返回按钮和面包屑
- column-card 改为独立样式

---

## 📋 建议修复优先级

| 优先级 | 问题编号 | 说明 |
|--------|---------|------|
| P0 | 1,2,4 | 运行即报错，必须立即修 |
| P0 | 3,9 | 种子数据问题 |
| P1 | 5,6,7 | 违反 Win7/IE11 核心约束 |
| P2 | 8 | emoji 兼容性 |
| P3 | 10,11 | 权限和菜单完整性 |
| P4 | 12 | CSS 清理 |
