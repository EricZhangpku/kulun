#!/usr/bin/env python3
import os
import sys
import csv
import re
import json
import time
import threading
import urllib.request
import argparse

try:
    from importlib.metadata import version as _get_version
    __version__ = _get_version("kulun")
except Exception:
    __version__ = "unknown"

try:
    import numpy as np
    import matplotlib.pyplot as plt
    import matplotlib.font_manager as fm
    from matplotlib.lines import Line2D
    from scipy.signal import savgol_filter
    from scipy.interpolate import interp1d
    HAS_LIBS = True
except ImportError:
    HAS_LIBS = False

def _get_songti_fonts():
    """Return available Chinese 宋体 (Song/serif) fonts on the current system."""
    candidates = [
        # Windows
        'SimSun', 'FangSong', 'KaiTi',
        # macOS
        'Songti SC', 'STSong', 'STFangsong',
        # Linux
        'Noto Serif CJK SC', 'AR PL UMing CN', 'AR PL UKai CN',
    ]
    available = {f.name for f in fm.fontManager.ttflist}
    return [name for name in candidates if name in available]


def _get_heiti_fonts():
    """Return available Chinese 黑体 (Hei/sans-serif) fonts on the current system."""
    candidates = [
        # Windows
        'SimHei', 'Microsoft YaHei',
        # macOS
        'Heiti TC', 'STHeiti', 'PingFang HK',
        # Linux
        'Noto Sans CJK SC', 'WenQuanYi Micro Hei', 'WenQuanYi Zen Hei',
    ]
    available = {f.name for f in fm.fontManager.ttflist}
    return [name for name in candidates if name in available]

# 30+ distinct colors for contrast overlay plots
_CONTRAST_COLORS = [
    '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
    '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf',
    '#e41a1c', '#377eb8', '#4daf4a', '#984ea3', '#ff7f00',
    '#a65628', '#f781bf', '#66c2a5', '#fc8d62', '#8da0cb',
    '#e78ac3', '#a6d854', '#ffd92f', '#e5c494', '#b3b3b3',
    '#1b9e77', '#d95f02', '#7570b3', '#e7298a', '#66a61e',
    '#e6ab02', '#a6761d', '#666666', '#b82e8a',
]

# 21 distinct marker shapes for contrast overlay data points
_MARKERS = ['o', 's', '^', 'D', 'v', '<', '>', 'p', '*', 'h',
            'H', '8', 'X', 'd', 'P', '+', 'x', '1', '2', '3', '4']


def _preprocess_args(argv):
    """Expand combined short options like -etd into separate arguments.

    Handles argument ordering so that flag-consuming options (e.g. -t)
    receive their positional arguments before trailing modifiers (e.g. -d).
    """
    known_combined = {
        'etd': ('et', ['-d']),
        'etu': ('et', ['-u']),
        'td': ('t', ['-d']),
        'tu': ('t', ['-u']),
    }
    known_combined = dict(sorted(known_combined.items(),
                                 key=lambda x: len(x[0]), reverse=True))

    new_argv = [argv[0]]
    i = 1
    while i < len(argv):
        arg = argv[i]
        if arg.startswith('-') and not arg.startswith('--') and len(arg) > 2:
            key = arg[1:]
            if key in known_combined:
                base, extras = known_combined[key]
                new_argv.append(f'-{base}')
                i += 1
                # consume non-option arguments that belong to the base flag
                while i < len(argv) and not argv[i].startswith('-'):
                    new_argv.append(argv[i])
                    i += 1
                # trailing modifiers go after the flag's arguments
                new_argv.extend(extras)
                continue
        new_argv.append(arg)
        i += 1
    return new_argv


def _detect_and_wrap_latex(text):
    """Auto-detect LaTeX formatting in legend labels and wrap for mathtext."""
    if '$' in text:
        return text
    if re.search(r'\\[a-zA-Z]+', text):
        return f'${text}$'
    return text


def _prompt_yes_no(prompt_text):
    """Prompt user for Y/n input, re-prompt on invalid input."""
    while True:
        answer = input(prompt_text).strip()
        if answer == '是' or answer.lower() == 'y':
            return True
        if answer == '否' or answer.lower() == 'n':
            return False
        print(f"输入错误: '{answer}'，请输入 Y/y (是) 或 N/n (否)。")


def _check_for_updates():
    """Background thread: check PyPI for newer versions (max once per day).

    Reads the last-check timestamp from ~/.cache/kulun/update-check.
    If the latest version on PyPI is newer than __version__, prints a
    one-line notice to stderr.
    """
    cache_dir = os.path.join(os.path.expanduser('~'), '.cache', 'kulun')
    cache_file = os.path.join(cache_dir, 'update-check')

    try:
        now = time.time()
        # 24-hour cooldown
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r') as f:
                    last = float(f.read().strip())
                if now - last < 86400:
                    return
            except (ValueError, OSError):
                pass

        pypi_url = 'https://pypi.org/pypi/kulun/json'
        req = urllib.request.Request(pypi_url, headers={'User-Agent': 'kulun'})
        with urllib.request.urlopen(req, timeout=3) as resp:
            info = json.loads(resp.read().decode())
        latest = info['info']['version']

        # Update cache
        os.makedirs(cache_dir, exist_ok=True)
        with open(cache_file, 'w') as f:
            f.write(str(now))

        if latest != __version__:
            print(
                f"\n[kulun] 新版本 {latest} 已发布（当前 {__version__}），"
                f"请运行 pip install --upgrade kulun 更新。\n"
                f"       具体更新内容与使用方法详见项目 GitHub 仓库："
                f"https://github.com/EricZhangpku/kulun\n",
                file=sys.stderr,
            )
    except Exception:
        # Never let an update check break the tool
        pass


def process_file_extract(file_path):
    if not file_path.endswith('.dat'):
        return None

    out_path = file_path[:-4] + '.csv'

    csv_data = []
    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) >= 5:
                try:
                    time_val = float(parts[3])
                    e_val = float(parts[4])
                    # skip trailing zeros (0.000000 0.000000)
                    if time_val == 0.0 and e_val == 0.0:
                        continue
                    csv_data.append([time_val, e_val])
                except ValueError:
                    continue

    with open(out_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Time(s)', 'E(mV)'])
        writer.writerows(csv_data)

    print(f"已提取，文件保存至: {out_path}")
    return out_path

def extract(paths, allow_dir=True):
    out_files = []
    for path in paths:
        if os.path.isdir(path):
            if not allow_dir:
                print(f"已跳过文件夹 {path}（-ec 模式不支持处理整个文件夹）。")
                continue
            all_entries = os.listdir(path)
            dat_files_list = [f for f in all_entries if f.endswith('.dat')]
            non_dat_files = [f for f in all_entries if not f.endswith('.dat')]
            if non_dat_files:
                print(f"文件夹中包含不支持转换的文件: {', '.join(non_dat_files)}")
            dat_files_list.sort()
            files = [os.path.join(path, f) for f in dat_files_list]
            for f in files:
                out = process_file_extract(f)
                if out: out_files.append(out)
        else:
            out = process_file_extract(path)
            if out: out_files.append(out)
    return out_files

def combine(csv_paths, out_filename=None):
    if not csv_paths:
        print("没有传入可供合并的 CSV 文件。")
        return

    combined_data = []
    current_max_t = 0.0

    for i, path in enumerate(csv_paths):
        if not path.endswith('.csv'):
            print(f"已跳过非 CSV 文件: {path}")
            continue

        with open(path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            header = next(reader, None) # skip header

            rows = []
            for row in reader:
                try:
                    t = float(row[0])
                    e = float(row[1])
                    rows.append([t, e])
                except (ValueError, IndexError):
                    continue

        if not rows: continue

        if i > 0:
            # If it's not the first file, remove the first row (assuming t=0.0)
            if rows[0][0] == 0.0:
                rows = rows[1:]

        local_max_t = 0.0
        for r in rows:
            adjusted_time = r[0] + current_max_t
            if r[0] > local_max_t:
                local_max_t = r[0]
            combined_data.append([adjusted_time, r[1]])

        current_max_t += local_max_t

    if not out_filename:
        out_filename = input("请输入合并后数据生成的保存文件名（例如 combined.csv）: ").strip()
        _, ext = os.path.splitext(out_filename)
        if not ext:
            out_filename += '.csv'

    with open(out_filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Time(s)', 'E(mV)'])
        writer.writerows(combined_data)

    print(f"合并后的数据已保存至: {out_filename}")
    return out_filename

def plot_csv(paths):
    if not HAS_LIBS:
        print("缺少绘图需要的 numpy, scipy, matplotlib 库，不能绘图。由于您当前环境中可能未安装，请使用如 pip install numpy scipy matplotlib 安装。")
        return

    # 自动检测系统中可用的中文字体，兼容 Windows / macOS / Linux
    songti_fonts = _get_songti_fonts()
    heiti_fonts = _get_heiti_fonts()
    # sans-serif：英文 Arial，中文黑体 — 用于标题、坐标轴、图例、刻度
    plt.rcParams['font.sans-serif'] = ['Arial'] + heiti_fonts + ['sans-serif']
    # serif：英文 Times New Roman，中文宋体 — 用于底部说明文字
    plt.rcParams['font.serif'] = ['Times New Roman'] + songti_fonts + ['serif']
    plt.rcParams['font.family'] = 'sans-serif'
    plt.rcParams['axes.unicode_minus'] = False
    plt.rcParams['mathtext.fontset'] = 'dejavusans'

    for path in paths:
        if not path.endswith('.csv'):
            print(f"跳过非 CSV 文件: {path}")
            continue

        try:
            data = np.loadtxt(path, delimiter=',', skiprows=1)
        except Exception as e:
            print(f"读取 {path} 失败: {e}")
            continue

        if len(data) == 0:
            continue

        times = data[:, 0]
        potentials = data[:, 1]

        # 如果相邻两个点之间电位上升超过 100mV，作为新的平行曲线的起点
        diff = np.diff(potentials)
        split_indices = np.where(diff > 100)[0] + 1
        segments = np.split(data, split_indices)

        print(f"\n正在处理 {path} (共自动识别到 {len(segments)} 条平行曲线):")
        print("提示：已采用 Savitzky-Golay 滤波方法：窗口点数 5，平滑参数 2 (对于曲线平滑)。")

        fig, ax1 = plt.subplots(figsize=(12, 7))
        ax2 = ax1.twinx()

        # 稍微增加横坐标范围，避免最右边文字越界
        ax1.set_xlim(times.min() - 5, times.max() + max(15, (times.max()-times.min())*0.05))

        # 为了保证投影文字不会在横轴以下甚至看不清，可以扩大底部留白
        y_min = potentials.min()
        y_max = potentials.max()
        ax1.set_ylim(y_min - (y_max - y_min)*0.15, y_max + (y_max - y_min)*0.05)

        jump_points = []
        last_t, last_E = None, None

        for i, segment_data in enumerate(segments):
            if len(segment_data) < 5:
                print(f"  - 警告：第 {i+1} 段曲线数据点不足5个。")
                continue

            t_seg = segment_data[:, 0]
            e_seg = segment_data[:, 1]

            # 画csv表格中的离散点（蓝圆点）
            ax1.plot(t_seg, e_seg, 'b.', label='Raw Data' if i==0 else "")

            # 平滑
            e_smooth = savgol_filter(e_seg, window_length=5, polyorder=2)

            # 用蓝色线条连接相邻两条曲线之间（上一条的结尾和本条的起点）
            if i > 0 and last_t is not None:
                ax1.plot([last_t, t_seg[0]], [last_E, e_smooth[0]], 'b-', alpha=0.5)

            # 蓝色线条画出平滑的曲线
            ax1.plot(t_seg, e_smooth, 'b-', label='Smoothed E' if i==0 else "")

            # 按照0.1s进行插值并求导
            if len(t_seg) > 1 and t_seg[-1] > t_seg[0]:
                f_interp = interp1d(t_seg, e_smooth, kind='cubic')
                t_interp = np.arange(t_seg[0], t_seg[-1]+0.001, 0.1)

                # 防止浮点误差导致的边界超限
                t_interp = t_interp[t_interp <= t_seg[-1]]
                e_interp = f_interp(t_interp)

                de_dt = np.gradient(e_interp, 0.1)

                # 细红线绘制一阶导曲线
                ax2.plot(t_interp, de_dt, 'r-', linewidth=1.0, alpha=0.8, label='dE/dt' if i==0 else "")

                # 寻找导数最负的点（突跃点）
                min_idx = np.argmin(de_dt)
                t_jump = t_interp[min_idx]
                de_jump = de_dt[min_idx]
                jump_points.append(t_jump)

                # 在导数图上标记出来
                ax2.plot(t_jump, de_jump, 'r^')

                # 虚线投影到横轴并标上时间
                ax1.axvline(x=t_jump, color='gray', linestyle='--', alpha=0.6)

                # 在投影线横轴下方写字（去掉s，放到横轴下面）
                ax1.text(t_jump, -0.015, f'{t_jump:.1f}', color='black', transform=ax1.get_xaxis_transform(),
                         ha='center', va='top', rotation=90, fontsize=10, clip_on=False)

            last_t = t_seg[-1]
            last_E = e_smooth[-1]

        ax1.set_xlabel('$t$ / s')
        ax1.set_ylabel('$E$ / mV', color='b')
        ax2.set_ylabel('d$E$/d$t$ / mV$\cdot$s$^{-1}$', color='r')

        ax1.tick_params(axis='y', labelcolor='b')
        ax2.tick_params(axis='y', labelcolor='r')

        default_title = f"Coulomb Titration Curve ({os.path.splitext(os.path.basename(path))[0]})"
        title_raw = input(f"请输入图片标题（支持 LaTeX 格式，敲下 Enter 则采用默认标题「{default_title}」): ").strip()
        if not title_raw:
            title_raw = default_title
        title_final = _detect_and_wrap_latex(title_raw)
        plt.title(title_final)

        # 将突跃点间隔放在图像底部左侧，不分行
        if len(jump_points) > 1:
            intervals = np.diff(jump_points)
            items = []
            for idx, interval in enumerate(intervals):
                items.append(f"第{idx+1}次与第{idx+2}次: {interval:.1f} s")

            info_str = "（突跃点时间间隔）   " + "      ".join(items)

            # 给底部预留一定的边距排版文字
            bottom_margin = 0.08
            fig.tight_layout(rect=[0, bottom_margin, 1, 1])

            # 添加文字到整张图片的底部靠左，紧贴图形区域
            fig.text(0.06, bottom_margin - 0.04, info_str, ha='left', va='bottom',
                     fontsize=11, fontfamily='serif')
        else:
            fig.tight_layout()

        # 图例
        if _prompt_yes_no("是否需要添加图例？(Y/n): "):
            default_legend = os.path.splitext(os.path.basename(path))[0]
            legend_raw = input(f"请输入图例名称（支持 LaTeX 格式，敲下 Enter 则采用默认名称「{default_legend}」): ").strip()
            if not legend_raw:
                legend_raw = default_legend
            legend_name = _detect_and_wrap_latex(legend_raw)
            legend_handle = Line2D([0], [0], color='b', linestyle='-', linewidth=1.5, label=legend_name)
            ax1.legend(handles=[legend_handle], loc='upper right', framealpha=0.9)

        png_path = os.path.splitext(path)[0] + '.png'
        plt.savefig(png_path, dpi=300)
        print(f"图像已保存至: {png_path}")
        plt.close(fig)


def contrast_plot(csv_paths, show_dots=False):
    """Overlay multiple CSV files on a single plot with smoothed fitting curves.

    Each CSV may contain one or more parallel curves (detected by potential
    jumps > 100 mV).  The user selects which curve to use per file and
    provides a legend name (plain text or LaTeX).  No derivative curves or
    jump-time annotations are drawn.
    """
    if not HAS_LIBS:
        print("缺少绘图需要的 numpy, scipy, matplotlib 库，不能绘图。"
              "请使用如 pip install numpy scipy matplotlib 安装。")
        return

    songti_fonts = _get_songti_fonts()
    heiti_fonts = _get_heiti_fonts()
    plt.rcParams['font.sans-serif'] = ['Arial'] + heiti_fonts + ['sans-serif']
    plt.rcParams['font.serif'] = ['Times New Roman'] + songti_fonts + ['serif']
    plt.rcParams['font.family'] = 'sans-serif'
    plt.rcParams['axes.unicode_minus'] = False
    plt.rcParams['mathtext.fontset'] = 'dejavusans'

    selected_data = []

    for path in csv_paths:
        if not path.endswith('.csv'):
            print(f"跳过非 CSV 文件: {path}")
            continue

        try:
            data = np.loadtxt(path, delimiter=',', skiprows=1)
        except Exception as e:
            print(f"读取 {path} 失败: {e}")
            continue

        if len(data) == 0:
            print(f"文件 {path} 数据为空，跳过。")
            continue

        times = data[:, 0]
        potentials = data[:, 1]

        diff = np.diff(potentials)
        split_indices = np.where(diff > 100)[0] + 1
        segments = np.split(data, split_indices)

        print(f"\n文件 {os.path.basename(path)} 共自动识别到 {len(segments)} 条曲线。")

        if len(segments) == 1:
            choice = 0
        else:
            while True:
                try:
                    raw = input(f"请选择使用第几条曲线 (1-{len(segments)}): ").strip()
                    choice = int(raw) - 1
                    if 0 <= choice < len(segments):
                        break
                    print(f"输入错误: 请输入 1 到 {len(segments)} 之间的数字。")
                except ValueError:
                    print(f"输入错误: '{raw}' 不是有效数字，请重新输入。")

        default_legend = os.path.splitext(os.path.basename(path))[0]
        legend_raw = input(f"请输入此曲线的图例名称 "
                           f"(支持 LaTeX 格式，敲下 Enter 则采用默认名称「{default_legend}」): ").strip()
        if not legend_raw:
            legend_raw = default_legend
        legend_name = _detect_and_wrap_latex(legend_raw)

        seg = segments[choice]
        if len(seg) < 5:
            print(f"  - 警告：第 {choice+1} 段曲线数据点不足5个，跳过。")
            continue
        selected_data.append((legend_name, seg[:, 0], seg[:, 1]))

    if len(selected_data) < 1:
        print("没有足够的数据可供绘图。")
        return

    fig, ax = plt.subplots(figsize=(12, 7))

    all_t_min, all_t_max = float('inf'), float('-inf')
    all_e_min, all_e_max = float('inf'), float('-inf')

    legend_handles = []

    for i, (name, t_seg, e_seg) in enumerate(selected_data):
        color = _CONTRAST_COLORS[i % len(_CONTRAST_COLORS)]
        marker = _MARKERS[i % len(_MARKERS)]

        if len(e_seg) < 5:
            continue
        e_smooth = savgol_filter(e_seg, window_length=5, polyorder=2)

        if show_dots:
            ax.plot(t_seg, e_seg, linestyle='None', marker=marker,
                    color=color, markersize=3, markeredgewidth=0.5,
                    alpha=0.8)
            ax.plot(t_seg, e_smooth, '-', color=color, linewidth=1.0)
            handle = Line2D([0], [0], color=color, marker=marker,
                            markersize=5, linestyle='-', linewidth=1.0,
                            label=name)
        else:
            ax.plot(t_seg, e_smooth, '-', color=color, linewidth=1.0,
                    label=name)

        if show_dots:
            legend_handles.append(handle)

        all_t_min = min(all_t_min, t_seg.min())
        all_t_max = max(all_t_max, t_seg.max())
        all_e_min = min(all_e_min, e_seg.min(), e_smooth.min())
        all_e_max = max(all_e_max, e_seg.max(), e_smooth.max())

    ax.set_xlim(all_t_min - 5,
                all_t_max + max(15, (all_t_max - all_t_min) * 0.05))
    ax.set_ylim(all_e_min - (all_e_max - all_e_min) * 0.08,
                all_e_max + (all_e_max - all_e_min) * 0.08)

    ax.set_xlabel('$t$ / s')
    ax.set_ylabel('$E$ / mV')

    if show_dots:
        ax.legend(handles=legend_handles, loc='upper right', framealpha=0.9)
    else:
        ax.legend(loc='upper right', framealpha=0.9)

    default_title = "Contrast Overlay"
    title_raw = input(f"请输入图片标题（支持 LaTeX 格式，敲下 Enter 则采用默认标题「{default_title}」): ").strip()
    if not title_raw:
        title_raw = default_title
    plt.title(_detect_and_wrap_latex(title_raw))

    fig.tight_layout()

    base = os.path.splitext(csv_paths[0])[0]
    png_path = base + '_contrast.png'
    plt.savefig(png_path, dpi=300)
    print(f"\n对比图已保存至: {png_path}")
    plt.close(fig)


EPILOG = """
Examples：
数据处理与绘图（-e / -c / -ec / -p / -cp / -ecp）：
  kulun -e data.dat                从单个 .dat 文件提取数据为 CSV
  kulun -e ./data_folder/          批量提取文件夹内所有 .dat 文件
  kulun -c a.csv b.csv             按顺序合并多个 CSV 文件
  kulun -ec a.dat b.dat            提取多个 .dat 并合并为单个 CSV
  kulun -p data.csv                绘制滴定曲线及一阶导分析图
  kulun -cp a.csv b.csv            合并 CSV 并生成合并后的分析图
  kulun -ecp a.dat b.dat           提取、合并、绘图，一步到位
  
绘制对比图（-t / -et，可选参数 -d / -u）：
  kulun -t a.csv b.csv             叠加多条 CSV 拟合曲线（等效于 -tu）
  kulun -td a.csv b.csv            叠加对比图并显示不同形状的数据点
  kulun -tu a.csv b.csv            叠加对比图，仅曲线，不显示数据点
  kulun -et a.dat b.dat            提取 .dat 后叠加对比图（等效于 -etu）
  kulun -etd ./data_folder/        提取文件夹并叠加对比图（含数据点）
  kulun -etu a.dat b.dat           提取 .dat 后叠加对比图（仅曲线）

Project home: https://github.com/EricZhangpku/kulun
"""


def main():
    sys.argv = _preprocess_args(sys.argv)

    # Check for updates in a daemon thread (non-blocking, silent on failure)
    _update_thread = threading.Thread(target=_check_for_updates, daemon=True)
    _update_thread.start()

    parser = argparse.ArgumentParser(
        prog="kulun",
        description="库仑滴定 (Coulomb titration) .dat 数据处理与科研绘图工具。\n"
                    "支持提取、合并、绘制滴定曲线及一阶导数分析图、多曲线对比叠加。",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        '-v', '-V', '--version', action='version',
        version=f'kulun {__version__}',
        help="show program's version number and exit",
    )

    actions = parser.add_argument_group("操作模式（至少选一项）")
    actions.add_argument(
        '-e', '--extract', nargs='+', metavar='PATH',
        help="从 .dat 文件或整个文件夹中提取第4、5列数据，保存为同名的 .csv 文件",
    )
    actions.add_argument(
        '-c', '--combine', nargs='+', metavar='CSV',
        help="按顺序合并多个 .csv 文件，时间轴自动平移确保连续",
    )
    actions.add_argument(
        '-ec', '--extract-combine', nargs='+', metavar='DAT',
        help="提取多个 .dat 文件后按顺序合并（不支持文件夹）",
    )
    actions.add_argument(
        '-p', '--plot', nargs='+', metavar='CSV',
        help="绘制 CSV 文件的滴定曲线与一阶导分析图，自动识别平行曲线并标注突跃点",
    )
    actions.add_argument(
        '-cp', '--combine-plot', nargs='+', metavar='CSV',
        help="合并多个 CSV 文件并生成合并后的分析图",
    )
    actions.add_argument(
        '-ecp', '--extract-combine-plot', nargs='+', metavar='DAT',
        help="提取多个 .dat 文件, 合并, 绘图, 一步到位",
    )
    actions.add_argument(
        '-t', '--contrast', nargs='+', metavar='CSV',
        help="将多个 CSV 文件曲线叠加绘制对比图，自动拟合平滑曲线并添加图例。"
             "可额外传入 -d（写作 -td，显示数据点）或 -u（写作 -tu，仅曲线）",
    )
    actions.add_argument(
        '-et', '--extract-contrast', nargs='+', metavar='PATH',
        help="提取 .dat 文件并叠加绘制对比图（支持传入多个文件或文件夹）。"
             "可额外传入 -d（写作 -etd，显示数据点）或 -u（写作 -etu，仅曲线）",
    )

    contrast_opts = parser.add_argument_group(
        "对比图选项（配合 -t / -et 使用，不可单独使用）"
    )
    contrast_opts.add_argument(
        '-d', '--dotted', action='store_true',
        help="在对比图中显示各曲线的数据散点，不同曲线使用不同形状标记",
    )
    contrast_opts.add_argument(
        '-u', '--undotted', action='store_true',
        help="在对比图中仅显示拟合曲线，不显示数据散点（默认行为）",
    )

    args = parser.parse_args()

    if args.extract:
        extract(args.extract)
    elif args.combine:
        combine(args.combine)
    elif args.extract_combine:
        csv_files = extract(args.extract_combine, allow_dir=False)
        if csv_files:
            combine(csv_files)
    elif args.plot:
        plot_csv(args.plot)
    elif args.combine_plot:
        out_csv = combine(args.combine_plot)
        if out_csv:
            plot_csv([out_csv])
    elif args.extract_combine_plot:
        csv_files = extract(args.extract_combine_plot, allow_dir=False)
        if csv_files:
            out_csv = combine(csv_files)
            if out_csv:
                plot_csv([out_csv])
    elif args.extract_contrast:
        show_dots = args.dotted
        csv_files = extract(args.extract_contrast, allow_dir=True)
        if csv_files:
            all_csvs = list(csv_files)
            csv_set = set(os.path.realpath(p) for p in all_csvs)
            for path in args.extract_contrast:
                if os.path.isdir(path):
                    existing = sorted([
                        os.path.join(path, f) for f in os.listdir(path)
                        if f.endswith('.csv')
                    ])
                    for ecsv in existing:
                        real = os.path.realpath(ecsv)
                        if real not in csv_set:
                            fname = os.path.basename(ecsv)
                            if _prompt_yes_no(
                                f"检测到已有CSV文件 {fname}，"
                                f"是否一并加入对比图？(Y/n): "
                            ):
                                all_csvs.append(ecsv)
                                csv_set.add(real)
            if len(all_csvs) < 2:
                print("可供对比的 CSV 文件不足 2 个，无法绘制对比图。")
            else:
                contrast_plot(all_csvs, show_dots=show_dots)
    elif args.contrast:
        show_dots = args.dotted
        if len(args.contrast) < 2:
            print("对比模式需要至少 2 个 CSV 文件。")
        else:
            contrast_plot(args.contrast, show_dots=show_dots)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
