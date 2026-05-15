# kulun — 库仑滴定数据处理与科研绘图工具

[![PyPI version](https://img.shields.io/pypi/v/kulun)](https://pypi.org/project/kulun/)
[![Python](https://img.shields.io/pypi/pyversions/kulun)](https://pypi.org/project/kulun/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> **v2.2.0 已发布** — 重大更新：将底层绘图引擎从 matplotlib 迁移至 plotly，**彻底解决了中文字体在各操作系统上的兼容性问题**。新增化学式上下标支持（`_` `^` `{}`）、文件保存冲突智能检测、全命令文件类型校验与软报错、`-t` 命令支持文件夹及 dat/csv 混传、科研风格排版优化（封闭轴线、斜体正体、突跃点避让、自适应尺寸）。详见下方 [命令详解](#命令详解) 与 [GitHub Releases](https://github.com/EricZhangpku/kulun/releases)。

`kulun` 是一个用 Python 编写的命令行工具，专门用于提取、合并并绘制由 *北京大学化学与分子工程学院定量分析化学实验教学组* 开发的库仑滴定软件所生成的 `.dat` 数据文件。支持滴定曲线及一阶导数分析、多曲线对比叠加、突跃点自动标注，启动时自动检测 PyPI 新版本并提醒更新。

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

如果输出了版本号（如 `kulun 2.2.0`），说明安装成功。

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

**交互流程：** 程序会先询问图片标题（支持 `_` `^` `{}` 表示化学式，例如 `SO_4^{2-}` 表示 SO₄²⁻，敲下 Enter 则采用默认标题），随后询问是否需要添加图例（Y/n），若添加图例则进一步询问图例名称。

**输出图片包含：**
- 蓝色曲线：原始数据散点 & Savitzky-Golay 平滑曲线
- 红色曲线：一阶导数 d*E*/d*t*
- 红色三角：突跃点（导数极值点）
- 灰色虚线：突跃点在时间轴上的投影
- 图片底部：每条平行曲线的突跃时间间隔
- 可选：右上角图例
- 物理量斜体、单位正体；全封闭坐标轴；突跃点标注与横轴标题自动避让
- 图片横纵比自动适配曲线条数（1 条 1:1，多条 2:1）

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

> 将多个 CSV（或含 dat 的混合路径）的滴定曲线叠加在同一张图中，自动拟合平滑曲线并以不同颜色区分，右上角附有图例。**支持直接传入文件夹**，自动识别其中的 CSV 和 DAT 文件（若 DAT 已有对应 CSV 则直接使用，否则提示先转换）。

```bash
# 仅显示拟合曲线
kulun -t run1.csv run2.csv run3.csv

# 传入文件夹或混合路径
kulun -t ./data_folder/ run1.csv

# 同时显示数据散点，不同曲线使用不同形状标记
kulun -td run1.csv run2.csv run3.csv
```

等价写法：`-tu` = `-t` + `-u`（仅曲线，默认行为），`-td` = `-t` + `-d`（显示数据散点）。

**输出图片包含：**
- 多条不同颜色的平滑拟合曲线
- 可选的数据散点（`-d`），每条曲线使用不同的标记形状
- 右上角图例
- 全封闭坐标轴；物理量斜体、单位正体；1:1 正方尺寸

**交互流程：** 程序会先识别每个 CSV 中的平行曲线数量，若超过 1 条则让用户选择；随后询问每条曲线的图例名称（支持 `_` `^` `{}` 表示化学式，敲下 Enter 则采用 CSV 文件名）；最后询问图片标题（敲下 Enter 则采用默认标题「Contrast Overlay」）。

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

v2.2.0 已将绘图引擎从 matplotlib 迁移至 plotly，利用浏览器引擎的 CSS 字体回落机制处理中文，覆盖 Windows / macOS / Linux 的常见中文字体，无需用户手动配置。如果仍有问题，请提交 [Issue](https://github.com/EricZhangpku/kulun/issues)。

> 对于 Ubuntu / Debian 等中文字体可能缺失的 Linux 发行版，程序启动时会自动检测并提示安装：
> ```bash
> sudo apt-get install fonts-noto-cjk
> ```

### Q: 绘图时报错缺少库

`kulun` 依赖以下 Python 包（安装时会自动带上）：

| 包名 | 用途 |
|------|------|
| `numpy` | 数值计算 |
| `scipy` | 信号平滑与插值 |
| `plotly` | 绘图引擎 |
| `kaleido` | 静态图像导出（PNG） |

如果你用了虚拟环境，请确认已激活：

```bash
# 先激活虚拟环境，再安装
pip install kulun
```

### Q: 如何在标题/图例中表示化学式

使用 `_` `^` `{}` 即可，例如 `SO_4^{2-}` 渲染为 SO₄²⁻，`Fe_2O_3` 渲染为 Fe₂O₃。程序启动时会给出示例提示。

### Q: 文件已存在时会发生什么

程序会自动检测同名文件（包括 `xxx(1).csv` 等编号变体），列出全部已有文件并询问是否替换。选择 n 后按 Enter 会自动采用下一个可用编号。

### Q: 传入了不支持的文件类型

程序会对每个命令校验传入的文件类型——例如 `-c` / `-p` 只能接受 CSV，`-e` 只能接受 DAT。若类型不匹配，会给出明确提示（如 "请先通过 -e 将 .dat 转换为 CSV 格式"）。文件不存在时也会有软报错而非 traceback。

### Q: 图片坐标轴数字太小或排版不美观

排版已按科研绘图标准优化（全封闭坐标轴、物理量斜体单位正体、曲线粗度 2× 坐标轴、尺寸自适应）。如需进一步定制，请提交 [Issue](https://github.com/EricZhangpku/kulun/issues)。

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

---

[Full documentation on GitHub](https://github.com/EricZhangpku/kulun)
