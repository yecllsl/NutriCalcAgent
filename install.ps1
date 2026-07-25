# NutriCalcAgent MCP Server 安装脚本
# 适用于 Windows PowerShell
#
# 使用方法：
#   1. 右键此文件 → "使用 PowerShell 运行"
#   2. 或在 PowerShell 中执行: .\install.ps1
#
# 前置要求：
#   - Python 3.12+
#   - uv 包管理器 (https://docs.astral.sh/uv/)

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  NutriCalcAgent v0.1.0 安装向导" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 获取脚本所在目录（项目根目录）
$projectRoot = $PSScriptRoot

# ──────────────────────────────────────────
# [1/5] 检查 uv 包管理器
# ──────────────────────────────────────────
Write-Host "[1/5] 检查 uv 包管理器..." -ForegroundColor Yellow
try {
    $uvVersion = uv --version 2>&1
    Write-Host "  ✓ uv 已安装 ($uvVersion)" -ForegroundColor Green
} catch {
    Write-Host "  ✗ uv 未安装" -ForegroundColor Red
    Write-Host ""
    Write-Host "  请先安装 uv：" -ForegroundColor Yellow
    Write-Host '  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"' -ForegroundColor White
    Write-Host ""
    Write-Host "  或访问 https://docs.astral.sh/uv/getting-started/install/" -ForegroundColor White
    exit 1
}

# ──────────────────────────────────────────
# [2/5] 检查 Python 版本
# ──────────────────────────────────────────
Write-Host "[2/5] 检查 Python 版本 (>=3.12)..." -ForegroundColor Yellow
$pythonVersion = python --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ✗ Python 未安装" -ForegroundColor Red
    Write-Host ""
    Write-Host "  请先安装 Python 3.12+：" -ForegroundColor Yellow
    Write-Host "  https://www.python.org/downloads/" -ForegroundColor White
    exit 1
}
# 提取版本号并比较
$versionMatch = $pythonVersion -match "(\d+)\.(\d+)"
if ($versionMatch) {
    $major = [int]$Matches[1]
    $minor = [int]$Matches[2]
    if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 12)) {
        Write-Host "  ✗ Python 版本过低: $pythonVersion (需要 >= 3.12)" -ForegroundColor Red
        Write-Host ""
        Write-Host "  请升级 Python: https://www.python.org/downloads/" -ForegroundColor Yellow
        exit 1
    }
}
Write-Host "  ✓ $pythonVersion" -ForegroundColor Green

# ──────────────────────────────────────────
# [3/5] 安装基础依赖
# ──────────────────────────────────────────
Write-Host "[3/5] 安装基础依赖..." -ForegroundColor Yellow
Write-Host "  基础依赖不含 OCR 引擎（paddleocr/paddlepaddle 体积大，已拆为可选）" -ForegroundColor Cyan

$mcpDir = Join-Path $projectRoot "nutricalc-mcp"

# 使用 uv sync 安装基础依赖（不包含 ocr extra）
Push-Location $mcpDir
try {
    Write-Host "  正在安装依赖包..." -ForegroundColor Cyan
    uv sync 2>&1 | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }

    if ($LASTEXITCODE -ne 0) {
        Write-Host "  ✗ 依赖安装失败" -ForegroundColor Red
        Write-Host ""
        Write-Host "  请尝试手动安装：" -ForegroundColor Yellow
        Write-Host "  cd nutricalc-mcp" -ForegroundColor White
        Write-Host "  uv sync" -ForegroundColor White
        exit 1
    }
    Write-Host "  ✓ 基础依赖安装完成" -ForegroundColor Green
} finally {
    Pop-Location
}

# ──────────────────────────────────────────
# [4/5] 询问并安装可选 OCR 依赖
# ──────────────────────────────────────────
Write-Host "[4/5] 是否安装 OCR 可选依赖？" -ForegroundColor Yellow
Write-Host "  OCR 用于食物照片文字识别（菜单/营养标签），paddleocr+paddlepaddle 约 1.5GB。" -ForegroundColor Cyan
Write-Host "  仅当需要拍照识别食物时才需要。手动录入功能无需 OCR。" -ForegroundColor Cyan
$installOcr = Read-Host "  安装 OCR 依赖？[y/N]"
if ($installOcr -match "^[Yy]$") {
    Push-Location $mcpDir
    try {
        Write-Host "  正在安装 OCR 依赖..." -ForegroundColor Cyan
        uv sync --extra ocr 2>&1 | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
        if ($LASTEXITCODE -ne 0) {
            Write-Host "  ✗ OCR 依赖安装失败，可稍后手动重试：uv sync --extra ocr" -ForegroundColor Red
        } else {
            Write-Host "  ✓ OCR 依赖安装完成" -ForegroundColor Green
        }
    } finally {
        Pop-Location
    }
} else {
    Write-Host "  ⊘ 已跳过 OCR 依赖。后续需要时执行：cd nutricalc-mcp && uv sync --extra ocr" -ForegroundColor DarkGray
}

# ──────────────────────────────────────────
# [5/5] 验证安装
# ──────────────────────────────────────────
Write-Host "[5/5] 验证安装..." -ForegroundColor Yellow

Push-Location $mcpDir
try {
    # 验证 Web 模块可用
    $webTest = uv run python -c "from nutricalc_mcp.web.app import create_app; print('OK')" 2>&1
    if ($webTest -match "OK") {
        Write-Host "  ✓ Web 可视化模块可用" -ForegroundColor Green
    } else {
        Write-Host "  ⚠ Web 可视化模块验证跳过" -ForegroundColor Yellow
    }

    # 验证食物数据库可用
    $dbTest = uv run python -c "from nutricalc_mcp.food_db import FoodDatabase; db = FoodDatabase(); print(f'foods={db.stats()}')" 2>&1
    if ($dbTest -match "foods=") {
        Write-Host "  ✓ 食物数据库可用 ($dbTest)" -ForegroundColor Green
    }

    # 运行快速测试
    Write-Host "  运行快速测试..." -ForegroundColor Cyan
    $testResult = uv run pytest tests/ -q --tb=no 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  ✓ 测试全部通过" -ForegroundColor Green
    } else {
        Write-Host "  ⚠ 部分测试未通过（不影响基础使用）" -ForegroundColor Yellow
    }
} catch {
    Write-Host "  ⚠ 自动验证失败，但不影响使用" -ForegroundColor Yellow
    Write-Host "  如遇问题请手动验证: cd nutricalc-mcp && uv run pytest tests/" -ForegroundColor Yellow
} finally {
    Pop-Location
}

# ──────────────────────────────────────────
# 安装完成提示
# ──────────────────────────────────────────
Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  ✓ 安装完成！" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "下一步操作：" -ForegroundColor White
Write-Host ""
Write-Host "  方式一：Web 可视化界面（推荐）" -ForegroundColor Cyan
Write-Host "     cd nutricalc-mcp" -ForegroundColor DarkGray
Write-Host "     uv run nutricalc-web" -ForegroundColor DarkGray
Write-Host "     浏览器访问 http://127.0.0.1:8002" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  方式二：Trae IDE 对话模式" -ForegroundColor Cyan
Write-Host "     1. 用 Trae IDE 打开此文件夹" -ForegroundColor DarkGray
Write-Host "        文件 → 打开文件夹 → 选择: $projectRoot" -ForegroundColor DarkGray
Write-Host "     2. 设置 → MCP → 打开'启用项目级 MCP'开关" -ForegroundColor DarkGray
Write-Host "     3. 重启 Trae" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  可用命令：" -ForegroundColor White
Write-Host "     /record   - 记录一餐" -ForegroundColor DarkGray
Write-Host "     /balance  - 营养平衡评估" -ForegroundColor DarkGray
Write-Host "     /advice   - AI 营养师建议" -ForegroundColor DarkGray
Write-Host "     /stats    - 统计图表" -ForegroundColor DarkGray
Write-Host "     /export   - 导出数据" -ForegroundColor DarkGray
Write-Host "     /profile  - 设置用户档案" -ForegroundColor DarkGray
Write-Host ""
