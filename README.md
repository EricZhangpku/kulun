# `kulun` — 库仑滴定数据处理与科研绘图工具

[![PyPI version](https://img.shields.io/pypi/v/kulun)](https://pypi.org/project/kulun/)
[![Python](https://img.shields.io/pypi/pyversions/kulun)](https://pypi.org/project/kulun/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> **v2.0.0 已发布** — 新增多曲线对比叠加绘图（`-t` / `-et`）、更新自动检测提醒、文件夹智能识别等多项功能。详见下方 [命令详解](#命令详解) 与 [GitHub Releases](https://github.com/EricZhangpku/kulun/releases)。

`kulun` 是一个用 Python 编写的命令行工具，专门用于提取、合并并绘制由 *北大化院定分实验教学组* 开发的库仑滴定软件所生成的 `.dat` 数据文件。支持滴定曲线及一阶导数分析、多曲线对比叠加、突跃点自动标注，启动时自动检测 PyPI 新版本并提醒更新。

---

## 目录

- [安装](#安装)
- [快速开始](#快速开始)
- [命令详解](#命令详解)
  - [1. 提取数据 `-e`](#1-提取数据--e)
  - [2. 合并数据 `-c`](#2-合并数据--c)
  - [3. 提取 + 合并 `-ec`](#3-提取--合并--ec)
  - [4. 绘制科研图 `-p`](#4-绘制科研图--p)
  - [5. 合并 + 绘图 `-cp`](#5-合并--绘图--cp)
  - [6. 一步到位 `-ecp`](#6-一步到位--ecp)
  - [7. 多曲线对比图 `-t`](#7-多曲线对比图--t)
  - [8. 提取 + 对比 `-et`](#8-提取--对比--et)
- [常见问题](#常见问题)
- [从源码安装（开发者）](#从源码安装开发者)
- [许可证](#许可证)

---

## 安装

确保电脑上已安装 Python 3.7 或更高版本，然后在终端中运行：

```bash
pip install kulun
```

安装完成后，在终端输入以下命令验证是否成功：

```bash
kulun --version
```

如果输出了版本号（如 `kulun 2.0.0`），说明安装成功。

> *如果你是第一次接触终端*——
> - **Windows**: 按 `Win(⊞) + R`，输入 "cmd" 回车。
> - **macOS**: 按 `Command(⌘) + 空格`，搜索 "终端" 或 "Terminal" 并打开。

---

## 快速开始

下面用一个典型的数据处理流程演示 `kulun` 的用法：

```bash
# 第 1 步：将 .dat 文件提取为表格
kulun -e my_data.dat
# → 生成 my_data.csv

# 第 2 步：绘制滴定曲线和一阶导数图
kulun -p my_data.csv
# → 生成 my_data.png（300 dpi 科研插图）
```

如果你有多个 `.dat` 文件需要**顺序**拼接后再出图，可以用以下代码一行搞定：

```bash
kulun -ecp file1.dat file2.dat file3.dat
# → 提取 → 合并 → 绘图，一步完成
```

如果你需要将**多次独立实验**的滴定曲线叠加在**同一张图**中对比：

```bash
# 直接对比已提取的 CSV
kulun -t run1.csv run2.csv run3.csv

# 或一步到位：提取 .dat 并叠加对比
kulun -et run1.dat run2.dat run3.dat

# 显示数据散点（不同曲线使用不同形状）
kulun -td run1.csv run2.csv
```

---

## 命令详解

### 1. 提取数据 `-e`

> 从库仑滴定仪导出的 `.dat` 文件中提取时间和电位两列数据，保存为 `.csv` 表格。

```bash
# 处理单个文件
kulun -e sample.dat

# 处理整个文件夹里的所有 .dat 文件
kulun -e ./data_folder/
```

| 输入 | 输出 |
|------|------|
| `sample.dat` | `sample.csv` |

---

### 2. 合并数据 `-c`

> 将多次实验的 CSV 文件按顺序拼接成一个，时间轴自动连续平移。

```bash
kulun -c part1.csv part2.csv part3.csv
```

程序会交互式询问合并后的文件名（比如输入 `combined.csv`）。

> **注意：** 文件的传入顺序很重要，请按照实验进行的先后顺序排列。

---

### 3. 提取 + 合并 `-ec`

> `-e` + `-c` 的组合方法：先提取每个 `.dat`，再合并成一个 CSV。

```bash
kulun -ec run1.dat run2.dat run3.dat
```

> **注意：** 此模式下**不支持传入文件夹**，请逐个指定 `.dat` 文件。

---

### 4. 绘制科研图 `-p`

> 对 CSV 数据绘图，自动识别平行滴定曲线、计算一阶导数、标注突跃点时间。

```bash
kulun -p data.csv
```

**输出图片包含：**
- 蓝色曲线：原始数据 & Savitzky-Golay 平滑曲线
- 红色曲线：一阶导数 d*E*/d*t*
- 红色三角：突跃点（导数极值点）
- 灰色虚线：突跃点在时间轴上的投影
- 图片底部：每条平行曲线的突跃时间间隔

---

### 5. 合并 + 绘图 `-cp`

> `-c` + `-p` 的组合方法：合并多个 CSV，再绘制合并后的总图。

```bash
kulun -cp part1.csv part2.csv part3.csv
```

---

### 6. 一步到位 `-ecp`

> `kulun` 一步到位的命令：把原始 `.dat` 文件直接变成科研插图。

```bash
kulun -ecp run1.dat run2.dat run3.dat
```

等价于手动执行：

```bash
# -ecp 内部自动完成以下三步：
kulun -ec run1.dat run2.dat run3.dat   # 提取 + 合并
kulun -p combined.csv                  # 绘图
```

---

### 7. 多曲线对比图 `-t`

> 将多个 CSV 文件的滴定曲线叠加在同一张图中，自动拟合平滑曲线并以不同颜色区分，右上角附有图例。

```bash
# 仅显示拟合曲线
kulun -t run1.csv run2.csv run3.csv

# 同时显示数据散点，不同曲线使用不同形状标记
kulun -td run1.csv run2.csv run3.csv
```

等价写法：`-tu` = `-t` + `-u`（仅曲线，默认行为），`-td` = `-t` + `-d`（显示数据散点）。

**输出图片包含：**
- 多条不同颜色的平滑拟合曲线
- 可选的数据散点（`-d`），每条曲线使用不同的标记形状
- 右上角图例：支持普通文本与 LaTeX 格式（自动识别）
- 自动询问每条曲线的图例名称（敲下 Enter 则直接使用 CSV 文件名）

**交互流程：** 程序会先识别每个 CSV 中的平行曲线数量，若超过 1 条则让用户选择；随后询问每条曲线的图例名称（敲下 Enter 则直接使用 CSV 文件名），支持空格、特殊字符或 LaTeX 公式。

---

### 8. 提取 + 对比 `-et`

> `-e` + `-t` 的组合方法：先提取 `.dat`，再叠加绘制对比图。**支持直接传入文件夹**。

```bash
# 从多个 .dat 文件一步生成对比图
kulun -et run1.dat run2.dat run3.dat

# 使用文件夹：自动提取所有 .dat，并询问是否包含已有的 .csv
kulun -et ./data_folder/

# 含数据点版本
kulun -etd run1.dat run2.dat
```

等价写法：`-etu` = `-et` + `-u`（默认行为），`-etd` = `-et` + `-d`。

> **文件夹智能识别：** 程序会列出文件夹中无法转换的非 `.dat` 文件，若发现已有 `.csv` 文件，会逐个询问是否一并加入对比图，避免重复提取。

---

## 常见问题

### Q: 安装时报错 `pip: command not found`

说明电脑上还没有 Python。请先去 [python.org](https://www.python.org/downloads/) 下载安装 Python（安装时勾选 "Add Python to PATH"），然后再运行 `pip install kulun`。

### Q: 绘图中文显示为方框

这是字体问题，`kulun` 已自动适配 Windows / macOS / Linux 的中文字体（宋体/黑体），一般不需要额外配置。如果仍有问题，请提交 [Issue](https://github.com/EricZhangpku/kulun/issues)。

### Q: 绘图时报错缺少库

`kulun` 依赖 `numpy`、`scipy`、`matplotlib`，安装时会自动带上。如果你用了虚拟环境，请确认已激活：

```bash
# 先激活虚拟环境，再安装
pip install kulun
```

### Q: 图片坐标轴数字太小或排版不美观

这是为了兼顾多条平行曲线的复杂场景而做的自动布局。如果需要定制，请提交 [Issue](https://github.com/EricZhangpku/kulun/issues) 说明具体需求。

### Q: 如何卸载

```bash
pip uninstall kulun
```

### Q: 程序启动时提示新版本

`kulun` v2.0 起内置了自动更新检测：启动时后台静默查询 PyPI，若发现新版本会在终端打印提醒（24 小时内不会重复检查）。运行以下命令即可更新：

```bash
pip install --upgrade kulun
```

---

## 从源码安装（开发者）

```bash
git clone https://github.com/EricZhangpku/kulun.git
cd kulun
pip install -e .
```

---

## 许可证

MIT License · [EricZhangpku](https://github.com/EricZhangpku)
