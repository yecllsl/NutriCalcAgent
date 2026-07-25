# NutriCalcAgent - AI 驱动的本地营养师 Agent

基于 MCP（Model Context Protocol）架构的中文营养师 Agent，帮助用户通过拍照或手动录入食物，自动分析营养成分、评估膳食平衡、生成个性化营养建议。所有数据本地存储，隐私优先，无需联网。

参考 [DeepReview](../DeepReview) 项目的分层架构设计，采用"MCP 服务层 + Web 可视化层 + Trae 配置层"分离模式。

## 核心功能

- 🍱 **食物记录**: 拍照识别菜品 / 手动输入 / OCR 营养标签识别
- 🔬 **营养分析**: 基于《中国食物成分表》查表 + LLM 估算兜底，覆盖 18 种核心营养素
- ⚖️ **平衡评估**: 日/周/月时序分析，对《中国居民膳食营养素参考摄入量》达成率评分
- 📊 **统计可视化**: 30 天能量趋势、营养雷达图、餐次分布、食物类别分布
- 🤖 **AI 营养师**: 三种人设（专业/温柔/严格），多轮对话式建议，下一餐推荐
- 📋 **数据导出**: JSON / CSV 格式，导出前需用户确认
- 🌐 **Web 界面**: 本地浏览器 http://127.0.0.1:8002，HTMX 局部刷新 + ECharts 图表

## 系统架构

```
用户交互层
├── 对话式交互 (命令: /record /analyze /balance /advice /stats /export /profile)
├── Web 可视化界面 (本地浏览器 http://127.0.0.1:8002)
└── MCP 客户端 (Trae IDE / Cursor / 任意 MCP Host)
    ↓
Skills 编排层 (.trae/skills/: meal-record / nutrition-analyze / balance-review / nutritionist-consult / data-export)
    ↓
MCP Tools 层 (nutricalc-mcp, 12 个 Tools)
├── Web 可视化子模块 (FastAPI + HTMX + ECharts)
    ↓
Rules 约束层 (.trae/rules/: nutrition / classification / data-safety / interaction)
    ↓
数据存储层 (本地 JSON 文件, 原子写入, 零外部依赖)
```

## 技术栈

| 组件 | 技术选型 | 说明 |
|------|---------|------|
| MCP Server | Python 3.12+ / FastMCP | 标准化工具协议，LLM 无关 |
| Web 可视化 | FastAPI + HTMX + ECharts | 局部刷新，无前端构建链 |
| 数据模型 | Pydantic 2 | 类型安全 + 自动校验 |
| 食物数据库 | 中国食物成分表（第 6 版） | 本地 JSON，离线可用 |
| OCR 引擎（可选） | PaddleOCR | 本地部署，无需 API Key |
| 数据存储 | JSON 文件 | 原子写入，零外部依赖 |
| 包管理 | uv | 现代高速 Python 包管理器 |
| 测试 | pytest + pytest-asyncio | 64 个单元/集成测试 |

## 快速安装

### 前置要求

- Python 3.12+
- [uv 包管理器](https://docs.astral.sh/uv/)（Windows: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`）
- Trae IDE CN（可选，用于 MCP 对话式交互）

### 安装步骤

#### 1. 运行安装脚本

```powershell
# Windows PowerShell
.\install.ps1
```

安装脚本会自动检查环境、创建虚拟环境并安装所有依赖。

> ⏱️ 首次安装约 1-2 分钟。OCR 引擎（PaddleOCR 约 1.5GB）为可选依赖，脚本会询问是否安装。

#### 2. 在 Trae IDE 中配置（可选）

1. 用 Trae IDE 打开项目文件夹
2. 进入 **设置 → MCP**
3. 打开 **"启用项目级 MCP"** 开关
4. 重启 Trae

> 💡 项目级 MCP 配置位于 `.trae/mcp.json`，使用 `${workspaceFolder}` 变量自动适配路径。

#### 3. 开始使用

**对话模式（Trae IDE 中）:**
```
/record   - 记录一餐（拍照/手动）
/balance  - 评估营养平衡
/advice   - AI 营养师建议
/stats    - 查看统计图表
/export   - 导出数据
/profile  - 设置用户档案
```

**Web 界面模式:**
```powershell
cd nutricalc-mcp
uv run nutricalc-web
```
浏览器访问 http://127.0.0.1:8002

### 可选：安装 OCR 引擎

OCR 引擎用于食物照片中的文字识别（菜单/营养标签），**非必需**。仅使用手动录入时无需安装：

```powershell
cd nutricalc-mcp
uv sync --extra ocr
```

未安装时调用 OCR 会得到友好提示并降级为手动输入，不影响其他功能。

## 使用方法

### 命令模式

| 命令 | 功能 |
|------|------|
| `/record` | 记录一餐（拍照识别 / 手动输入食物名称+份量） |
| `/balance` | 营养平衡评估（日/周/月） |
| `/advice` | AI 营养师个性化建议（三种人设） |
| `/stats` | 统计分析（日期/餐次/类别/营养素维度） |
| `/export` | 导出饮食数据（JSON/CSV） |
| `/profile` | 设置用户档案（年龄/性别/身高/体重/目标） |

### 自然语言模式

- "帮我记录这顿午餐" → 触发 `/record`
- "我这周营养均衡吗" → 触发 `/balance`
- "营养师，我今天能吃甜点吗" → 触发 `/advice`
- "看看我的饮食统计" → 触发 `/stats`

### Web 可视化界面

启动 Web 服务后，访问 http://127.0.0.1:8002 可使用五大功能页面：

1. **概览 Dashboard**: 今日能量/目标达成率、近期记录、30 天趋势、营养雷达图
2. **饮食记录**: 录入表单 + 记录列表（支持筛选、删除、HTMX 局部刷新）
3. **统计图表**: 能量趋势、营养雷达、餐次分布、食物类别分布
4. **平衡分析**: 周期评估、营养缺口、平衡评分、AI 建议入口
5. **用户档案**: 个性化参数设置（性别/年龄/体重/活动水平/健康目标）

> 💡 Web 服务仅绑定 `127.0.0.1`，所有数据本地存储，JS 库本地化（HTMX / ECharts），**无任何外部请求**。

## 项目结构

```
NutriCalcAgent/
├── nutricalc-mcp/                          # 纯 MCP Server (通用服务层)
│   ├── src/nutricalc_mcp/
│   │   ├── server.py                       # FastMCP 服务入口 (12 个 Tools)
│   │   ├── models.py                       # Pydantic 数据模型
│   │   ├── storage.py                      # JSON 存储引擎（原子写入、部分更新）
│   │   ├── food_db.py                      # 中国食物成分表本地库
│   │   ├── knowledge_map.py                # 营养知识图谱 + RNI 参考值
│   │   ├── tools/                          # 8 个业务 Tools
│   │   │   ├── crud.py                     # 饮食记录 CRUD
│   │   │   ├── food_recognize.py           # 食物识别（OCR + 多模态 prompt）
│   │   │   ├── nutrition_analyze.py        # 营养成分分析
│   │   │   ├── balance_assess.py           # 营养平衡评估
│   │   │   ├── statistics.py               # 多维统计 + 趋势 + 雷达图
│   │   │   ├── nutritionist.py             # AI 营养师建议
│   │   │   └── export.py                   # 数据导出
│   │   ├── prompts/                        # AI Prompt 模板
│   │   │   ├── food_recognize_prompt.py
│   │   │   ├── nutrition_analyze_prompt.py
│   │   │   ├── balance_assess_prompt.py
│   │   │   └── nutritionist_prompt.py
│   │   └── web/                            # Web 可视化模块
│   │       ├── app.py                      # FastAPI 应用工厂
│   │       ├── services.py                 # Web 服务编排层
│   │       ├── routes/                     # 路由（dashboard/logs/stats/analysis/profile）
│   │       ├── templates/                  # Jinja2 模板
│   │       └── static/                     # 静态资源（HTMX/ECharts 本地化）
│   ├── tests/                              # 测试套件 (64 个用例)
│   │   ├── conftest.py                     # 共享 fixtures
│   │   ├── test_models.py                  # 数据模型测试
│   │   ├── test_storage.py                 # 存储引擎测试
│   │   ├── test_food_db.py                 # 食物数据库测试
│   │   ├── test_tools.py                   # 业务工具测试
│   │   └── test_web.py                     # Web API 集成测试
│   ├── data/                               # 运行时数据（被 .gitignore）
│   ├── pyproject.toml
│   └── uv.lock
│
├── .trae/                                  # Trae 配置与 Skills/Rules
│   ├── mcp.json                            # 项目级 MCP 配置
│   ├── skills/                             # 5 个 Skills
│   │   ├── meal-record/                    # /record
│   │   ├── nutrition-analyze/              # 营养分析
│   │   ├── balance-review/                 # /balance
│   │   ├── nutritionist-consult/           # /advice
│   │   └── data-export/                    # /export
│   └── rules/                              # 4 个 Rules
│       ├── nutrition-rules.md              # 营养分析规则
│       ├── classification-rules.md         # 食物分类规则
│       ├── data-safety-rules.md            # 数据安全规则
│       └── interaction-rules.md            # 交互规则
│
├── docs/                                   # 文档
│   └── 市场调研报告.md                      # 竞品分析 + 补充需求
├── install.ps1                             # Windows 安装脚本
├── README.md                               # 本文件
└── LICENSE                                 # MIT
```

## 架构设计说明

### 分层分离原则

| 层级 | 位置 | 用途 |
|------|------|------|
| **服务层** | `nutricalc-mcp/` | 纯 Python MCP Server，LLM 无关，可独立使用 |
| **Web 可视化层** | `nutricalc-mcp/src/nutricalc_mcp/web/` | 本地 Web 界面，复用服务层逻辑 |
| **配置层** | `.trae/skills/`, `.trae/rules/` | Trae IDE 专用流程编排与约束规则 |

### MCP Tools 清单（12 个）

| 类别 | 工具 | 说明 |
|------|------|------|
| CRUD | `save_food_log` | 保存饮食记录（自动生成 ID） |
| CRUD | `query_food_logs` | 按餐次/类别/日期查询 |
| CRUD | `update_food_log` | 更新记录 |
| CRUD | `delete_food_log` | 删除记录 |
| 业务 | `recognize_food` | 食物识别（OCR + 多模态 prompt） |
| 业务 | `analyze_nutrition` | 营养成分分析（查表 + LLM 估算） |
| 业务 | `assess_balance` | 营养平衡评估（日/周/月） |
| 业务 | `get_statistics` | 多维统计 + 趋势 + 雷达图 |
| 业务 | `nutritionist_advice` | AI 营养师建议（3 种人设） |
| 业务 | `save_user_profile` | 保存用户档案 |
| 业务 | `load_user_profile` | 加载用户档案 |
| 业务 | `export_data` | 数据导出（JSON/CSV） |

### 营养知识体系

- **食物分类**: 谷薯类/蔬菜类/水果类/肉禽蛋类/奶豆类/水产类/坚果类/油脂类/调味品/混合菜/饮料类/其他
- **营养素覆盖**: 能量、蛋白质、脂肪、碳水、膳食纤维、VA/VC/VE/VB1/VB2/烟酸、钙/铁/锌/硒/钠/钾、胆固醇、GI
- **参考标准**: 《中国居民膳食营养素参考摄入量（2023版）》+《中国居民膳食指南（2022）》
- **评估规则**: 达成率 <80% RNI 为不足，钠/胆固醇 >150% 为过量，平衡评分 0-100

## 数据安全

- ✅ 所有饮食记录、用户档案、评估报告仅存储在本地 `data/` 目录
- ✅ 食物图片存储在项目目录下，不外传
- ✅ OCR 本地部署（PaddleOCR），不调用外部 OCR API
- ✅ Web 服务仅绑定 127.0.0.1，仅本机访问
- ✅ JS 库本地化（HTMX / ECharts），无 CDN 请求
- ✅ 导出数据前需用户确认
- ✅ 不记录用户姓名等个人身份信息，user_id 默认为 "default"
- ✅ 营养师建议 prompt 在本地构造，由 MCP 宿主 LLM 执行，不直接外传饮食数据

## 测试与开发

### 运行测试

```powershell
cd nutricalc-mcp
uv sync --extra dev
uv run pytest tests/ -v
```

测试覆盖：64 个单元/集成用例，覆盖模型、存储、食物库、工具层、Web API。

### 项目开发

```powershell
# 启动 Web 开发服务器（热重载）
cd nutricalc-mcp
uv run uvicorn nutricalc_mcp.web.app:create_app --factory --host 127.0.0.1 --port 8002 --reload

# 启动 MCP Server（stdio 模式，供 MCP 客户端连接）
cd nutricalc-mcp
uv run nutricalc-mcp
```

## 常见问题

### Q: 安装脚本报错 "uv 未安装"

```powershell
# 安装 uv (Windows)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### Q: MCP Server 不生效

1. 确认已在 Trae 中打开 **"启用项目级 MCP"** 开关
2. 确认已重启 Trae
3. 检查 `.trae/mcp.json` 路径是否正确

### Q: OCR / PaddleOCR 安装失败

- 确认 Python 版本 >= 3.12
- 确认网络畅通（需下载模型文件）
- OCR 为**可选依赖**，默认 `uv sync` 不会安装
- 若仅使用手动录入、统计分析等功能，**无需安装 OCR**

### Q: 食物库未命中怎么办

- 本地食物库覆盖常见中国食物（种子数据 + 中国食物成分表）
- 未命中时自动生成 LLM 估算 prompt，由 MCP 宿主 LLM 基于食材估算营养
- 用户也可手动输入食物名称，系统会尝试模糊匹配

## License

MIT License

## Contributing

欢迎提交 Issue 和 Pull Request！
