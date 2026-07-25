---
name: nutrition-analyze
description: Use when 用户想分析食物营养成分、查看营养素含量、估算菜品营养
---

# 营养成分分析流程

## Overview

对一组食物项执行营养成分分析，优先本地食物成分表查表，未命中时由 LLM 估算。

## When to Use

- 用户说"分析营养"、"这个菜有多少热量"、"查营养成分"
- 用户提供了食物名称和份量，需要计算营养素
- 用户想了解一餐的总营养摄入

## Workflow

### 1. 准备食物项
收集用户提供的食物项列表，每项需包含：
- name: 食物名称
- amount_g: 份量（克）
- cooking_method: 烹饪法（可选）
- category: 食物类别（可选）

### 2. 调用分析
调用 `analyze_nutrition` Tool，传入食物项列表。

### 3. 处理结果
- 命中本地库的项：直接展示营养素
- 未命中的项：使用返回的 `estimate_prompt` / `decompose_prompt` 调用 LLM 估算
  - 混合菜先拆解为食材（`decompose_prompt`）
  - 再按食材查表或估算（`estimate_prompt`）

### 4. 展示汇总
展示每项营养 + 整餐汇总（能量/蛋白/脂肪/碳水/纤维/钠等）。

## Quick Reference

| 步骤 | Tool | 说明 |
|------|------|------|
| 营养分析 | `analyze_nutrition` | 本地查表 + 未命中估算 prompt |
| 混合菜拆解 | LLM + `decompose_prompt` | 拆解为食材 |
| 营养估算 | LLM + `estimate_prompt` | 基于食材估算 |

## Common Mistakes

- **份量缺失**：amount_g 为 0 时无法计算，必须确认份量
- **忽略烹饪法**：炒/炸会额外加油脂，影响脂肪与能量估算
- **混合菜直接查表**：麻婆豆腐等混合菜应先拆解为食材再查表
