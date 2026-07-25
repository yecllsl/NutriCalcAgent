---
name: data-export
description: Use when 用户想导出饮食数据、备份数据、导出为Excel/CSV、迁移数据
---

# 数据导出流程

## Overview

将饮食记录、用户档案导出为 JSON / CSV，供用户备份或迁移。遵循数据安全规则：导出需用户确认。

## When to Use

- 用户说"导出数据"、"备份"、"导出Excel"、"下载数据"
- 用户想备份饮食记录
- 用户想在外部工具（Excel等）分析数据

## Workflow

### 1. 预览导出
调用 `export_summary`（通过 `export_data` 的预览模式），展示：
- 待导出记录数
- 食物项总数
- 日期范围
- 应用过滤条件（可选：meal_type/category/date_range）

### 2. 用户确认
向用户确认导出格式与范围：
- JSON：完整结构化（含嵌套营养素+用户档案），适合备份/迁移
- CSV：扁平化（每行一个食物项），适合 Excel 分析

### 3. 执行导出
调用 `export_data` Tool，返回：
- content: 导出内容字符串
- filename: 建议文件名
- needs_confirmation: True（提示需用户确认后外发）

### 4. 交付数据
将导出内容保存为文件或展示给用户（不外传）。

## Quick Reference

| 步骤 | Tool | 说明 |
|------|------|------|
| 导出预览 | `export_summary` | 统计待导出数据量 |
| 执行导出 | `export_data` | 生成 JSON/CSV 内容 |

## 约束规则

- 导出前必须经用户确认（数据安全规则）
- 导出数据不外传，仅生成本地文件/内容
- CSV 含 UTF-8 BOM 以兼容 Excel 中文显示
- JSON 导出包含 export_meta（时间戳/版本/记录数）
