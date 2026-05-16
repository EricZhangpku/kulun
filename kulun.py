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
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    from scipy.signal import savgol_filter, argrelextrema
    from scipy.interpolate import interp1d
    HAS_LIBS = True
except ImportError:
    HAS_LIBS = False

# CSS font-family strings for plotly figures.  The browser (or kaleido)
# resolves them left-to-right, so Latin text hits Arial / TNR first, and
# Chinese glyphs fall through to the platform-specific CJK font.
_SANS_FONT = ("Arial, 'Microsoft YaHei', "
              "'PingFang SC', 'PingFang HK', 'Heiti TC', STHeiti, "
              "'WenQuanYi Micro Hei', 'Noto Sans CJK SC', sans-serif")
_SERIF_FONT = ("Times New Roman, SimSun, "
               "'Songti SC', 'Songti SC Light', STSong, "
               "'Noto Serif CJK SC', 'AR PL UMing CN', serif")

_CJK_CHECKED = False


def _check_cjk_fonts():
    """Warn once if no CJK font files are detected on the current system."""
    global _CJK_CHECKED
    if _CJK_CHECKED:
        return
    _CJK_CHECKED = True

    if sys.platform == 'darwin':
        _dirs = ['/System/Library/Fonts/', '/System/Library/Fonts/Supplemental/',
                 '/Library/Fonts/']
        _patterns = ['PingFang', 'Heiti', 'Songti', 'STSong', 'STHeiti']
        _hint = "macOS 用户请确认系统字体未损坏。"
    elif sys.platform == 'win32':
        _windir = os.environ.get('WINDIR', 'C:\\Windows')
        _dirs = [os.path.join(_windir, 'Fonts')]
        _patterns = ['msyh', 'YaHei', 'SimHei', 'SimSun']
        _hint = "Windows 用户请确认已安装中文字体。"
    else:
        # Linux: prefer the fast fontconfig query
        try:
            import subprocess
            result = subprocess.run(
                ['fc-list', ':lang=zh'], capture_output=True, text=True, timeout=5)
            if result.stdout.strip():
                return  # CJK fonts available
        except Exception:
            pass
        # filesystem fallback
        _dirs = ['/usr/share/fonts/', '/usr/local/share/fonts/',
                 os.path.expanduser('~/.fonts/'),
                 os.path.expanduser('~/.local/share/fonts/')]
        _patterns = ['Noto', 'WenQuanYi', 'CJK', 'wqy', 'uming', 'ukai', 'Droid']
        _hint = ("Linux 用户请安装中文字体，例如：sudo apt-get install fonts-noto-cjk\n"
                 "        或 sudo yum install google-noto-cjk-fonts")

    for _d in _dirs:
        if not os.path.isdir(_d):
            continue
        try:
            _entries = os.scandir(_d)
        except OSError:
            continue
        with _entries:
            for _entry in _entries:
                if not _entry.is_file():
                    continue
                if not _entry.name.lower().endswith(('.ttf', '.otf', '.ttc')):
                    continue
                _low = _entry.name.lower()
                for _p in _patterns:
                    if _p.lower() in _low:
                        return  # found — all good

    print(f"警告：未检测到中文字体，中文可能无法正常显示。{_hint}",
          file=sys.stderr)

# Marker symbol mapping: matplotlib → plotly
_MARKER_MAP = {
    'o': 'circle', 's': 'square', '^': 'triangle-up', 'D': 'diamond',
    'v': 'triangle-down', '<': 'triangle-left', '>': 'triangle-right',
    'p': 'pentagon', '*': 'star', 'h': 'hexagon', 'H': 'hexagon2',
    '8': 'octagon', 'X': 'x-thin', 'd': 'diamond-wide', 'P': 'cross-thin',
    '+': 'cross', 'x': 'x', '1': 'line-ns', '2': 'line-ew',
    '3': 'line-ne', '4': 'line-nw',
}

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


def _format_sub_sup(text):
    """Convert ``_{...}`` / ``^{...}`` to HTML subscript / superscript tags.

    Example: ``SO_4^{2-}`` → ``SO<sub>4</sub><sup>2-</sup>``
    which plotly renders as SO₄²⁻ in the figure's native font.
    """
    text = re.sub(r'\_\{([^}]*)\}', r'<sub>\1</sub>', text)
    text = re.sub(r'\^\{([^}]*)\}', r'<sup>\1</sup>', text)
    # bare _x / ^x (single char, no braces)
    text = re.sub(r'\_(?!\{)(\S)', r'<sub>\1</sub>', text)
    text = re.sub(r'\^(?!\{)(\S)', r'<sup>\1</sup>', text)
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


def _safe_save_path(filepath):
    """Check *filepath* for existence; prompt to overwrite or rename.

    Scans for existing numbered siblings and suggests the next free
    number as the default.  Loops until a non-conflicting resolution
    is reached — every user-supplied name goes through the same
    replace-or-rename prompt.
    """
    if not os.path.exists(filepath):
        return filepath

    directory = os.path.dirname(filepath) or '.'
    base, ext = os.path.splitext(os.path.basename(filepath))

    # collect existing numbered siblings for the *original* base name
    existing = []
    i = 1
    while True:
        candidate = os.path.join(directory, f"{base}({i}){ext}")
        if os.path.exists(candidate):
            existing.append(os.path.basename(candidate))
            i += 1
        else:
            break
    next_num = i

    all_existing = [os.path.basename(filepath)] + existing
    existing_str = ", ".join(all_existing)
    replace_target = f" {os.path.basename(filepath)}" if existing else ""

    if _prompt_yes_no(f"文件 {existing_str} 已存在，是否替换{replace_target}？(Y/n): "):
        return filepath

    # loop: each iteration offers a numbered default and processes user input
    current_base = base
    current_ext = ext
    while True:
        # find first free numbered name for the current base
        j = 1
        while True:
            candidate = os.path.join(directory, f"{current_base}({j}){current_ext}")
            if not os.path.exists(candidate):
                break
            j += 1
        default_name = candidate

        raw = input(
            f"请输入新文件名（敲下 Enter 则采用"
            f"「{os.path.basename(default_name)}」）: "
        ).strip()

        if not raw:
            return default_name

        if not os.path.splitext(raw)[1]:
            raw += current_ext
        if not os.path.dirname(raw):
            raw = os.path.join(directory, raw)

        if not os.path.exists(raw):
            return raw

        # user-supplied name exists → ask, then loop again if declined
        if _prompt_yes_no(f"文件 {os.path.basename(raw)} 已存在，"
                          f"是否替换 {os.path.basename(raw)}？(Y/n): "):
            return raw

        # prepare for next iteration based on the rejected name
        current_base, current_ext = os.path.splitext(os.path.basename(raw))
        if not current_ext:
            current_ext = ext


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

    out_path = _safe_save_path(file_path[:-4] + '.csv')

    csv_data = []
    try:
        f = open(file_path, 'r', encoding='utf-8', errors='replace')
    except FileNotFoundError:
        print(f"文件不存在: {file_path}。"
              "请确保文件存在，并且处于正确的路径中。", file=sys.stderr)
        return None
    with f:
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
        if not os.path.exists(path):
            print(f"文件/文件夹不存在: {path}。请确保文件/文件夹存在，并且处于正确的路径中。", file=sys.stderr)
            continue
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
            if not path.endswith('.dat'):
                if path.endswith('.csv'):
                    print(f"{path} 是 CSV 文件，提取操作需要 .dat 文件。")
                else:
                    print(f"不支持的文件类型: {path}")
                continue
            out = process_file_extract(path)
            if out: out_files.append(out)
    return out_files

def combine(csv_paths, out_filename=None):
    if not csv_paths:
        print("没有传入可供合并的 CSV 文件。")
        return

    # folders are never accepted
    for path in csv_paths:
        if os.path.isdir(path):
            print(f"-c 命令不支持传递整个文件夹: {path}，请顺序传入文件。")
            return

    combined_data = []
    current_max_t = 0.0

    for i, path in enumerate(csv_paths):
        if not path.endswith('.csv'):
            if path.endswith('.dat'):
                print(f"{path} 是 .dat 文件，请先通过 -e 将其转换为 CSV 格式。")
            else:
                print(f"不支持的文件类型: {path}")
            continue
        if not os.path.exists(path):
            print(f"文件不存在: {path}。请确保文件存在，并且处于正确的路径中。", file=sys.stderr)
            continue

        try:
            f = open(path, 'r', encoding='utf-8')
        except FileNotFoundError:
            print(f"文件不存在: {path}。请确保文件存在，并且处于正确的路径中。", file=sys.stderr)
            continue
        with f:
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

    if len(combined_data) == 0:
        print("没有可供合并的有效 CSV 数据。")
        return

    if not out_filename:
        while True:
            out_filename = input("请输入合并后数据生成的保存文件名（例如 combined.csv）: ").strip()
            if out_filename:
                break
            print("名称不能为空，请重新输入。")
        _, ext = os.path.splitext(out_filename)
        if not ext:
            out_filename += '.csv'

    out_filename = _safe_save_path(out_filename)
    with open(out_filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Time(s)', 'E(mV)'])
        writer.writerows(combined_data)

    print(f"合并后的数据已保存至: {out_filename}")
    return out_filename

def plot_csv(paths):
    if not HAS_LIBS:
        print("缺少绘图需要的 numpy, scipy, plotly 库，不能绘图。"
              "请使用 pip install numpy scipy plotly kaleido 安装。")
        return

    _check_cjk_fonts()

    for path in paths:
        if os.path.isdir(path):
            print(f"不支持的文件类型: {path}（文件夹）")
            continue
        if not path.endswith('.csv'):
            if path.endswith('.dat'):
                print(f"{path} 是 .dat 文件，请先通过 -e 将其转换为 CSV 格式。")
            else:
                print(f"不支持的文件类型: {path}")
            continue
        if not os.path.exists(path):
            print(f"文件不存在: {path}。请确保文件存在，并且处于正确的路径中。", file=sys.stderr)
            continue

        try:
            data = np.loadtxt(path, delimiter=',', skiprows=1)
        except FileNotFoundError:
            print(f"文件不存在: {path}。请确保文件存在，并且处于正确的路径中。", file=sys.stderr)
            continue
        except Exception as e:
            print(f"读取 {path} 失败: {e}")
            continue

        if len(data) == 0:
            continue

        times = data[:, 0]
        potentials = data[:, 1]

        diff = np.diff(potentials)
        split_indices = np.where(diff > 100)[0] + 1
        segments = np.split(data, split_indices)

        print(f"\n正在处理 {path} (共自动识别到 {len(segments)} 条平行曲线):")
        print("提示：已采用 Savitzky-Golay 滤波方法：窗口点数 5，多项式阶数 2")

        n_curves = len(segments)
        # n=1 → 1:1,  n≥2 → 2:1
        fig_width = 600 if n_curves == 1 else 1000
        fig_height = 600 if n_curves == 1 else 500

        fig = make_subplots(specs=[[{"secondary_y": True}]])

        x_margin = max(35, (times.max() - times.min()) * 0.12)
        y_min, y_max = potentials.min(), potentials.max()
        y_pad = (y_max - y_min) * 0.10

        # Closed black axis box on all 4 sides
        _ax_line = dict(showline=True, linewidth=1.25, linecolor='black',
                        mirror=True, ticks='inside')
        _ax_font = dict(color='#1a1a1a', size=13)
        _ax_title = dict(size=15)

        fig.update_xaxes(range=[times.min() - 5, times.max() + x_margin],
                         **_ax_line)
        fig.update_yaxes(
            range=[y_min - y_pad, y_max + (y_max - y_min) * 0.05],
            title_text="<i>E</i> / mV",
            title_font=dict(color='#1a1a1a', **_ax_title),
            tickfont=_ax_font, secondary_y=False, **_ax_line,
        )

        jump_points = []
        last_t, last_E = None, None

        for i, segment_data in enumerate(segments):
            if len(segment_data) < 5:
                print(f"  - 警告：第 {i+1} 段曲线数据点不足5个。")
                continue

            t_seg = segment_data[:, 0]
            e_seg = segment_data[:, 1]

            # 离散点（深蓝色小圆点）
            fig.add_trace(go.Scatter(
                x=t_seg, y=e_seg, mode='markers',
                marker=dict(color='#1f77b4', symbol='circle', size=4),
                showlegend=False,
            ), secondary_y=False)

            # 平滑
            e_smooth = savgol_filter(e_seg, window_length=5, polyorder=2)

            # 连接相邻曲线（2× 坐标轴线宽）
            if i > 0 and last_t is not None:
                fig.add_trace(go.Scatter(
                    x=[last_t, t_seg[0]], y=[last_E, e_smooth[0]],
                    mode='lines', line=dict(color='#1f77b4', width=2.5),
                    opacity=0.4, showlegend=False,
                ), secondary_y=False)

            # 平滑曲线（2× 坐标轴线宽）
            fig.add_trace(go.Scatter(
                x=t_seg, y=e_smooth, mode='lines',
                line=dict(color='#1f77b4', width=2.5),
                showlegend=False,
            ), secondary_y=False)

            # 插值求导
            if len(t_seg) > 1 and t_seg[-1] > t_seg[0]:
                if len(np.unique(t_seg)) != len(t_seg):
                    print(f"  - 数据错误：第 {i+1} 段曲线的时间列中存在重复值"
                          f"（同一时间对应多个电位数据），无法进行插值求导，"
                          f"已跳过该段的一阶导数计算。")
                    last_t = t_seg[-1]
                    last_E = e_smooth[-1]
                    continue
                f_interp = interp1d(t_seg, e_smooth, kind='cubic')
                t_interp = np.arange(t_seg[0], t_seg[-1] + 0.001, 0.1)
                t_interp = t_interp[t_interp <= t_seg[-1]]
                e_interp = f_interp(t_interp)

                de_dt = np.gradient(e_interp, 0.1)

                # 一阶导曲线（与坐标轴线宽相同）
                fig.add_trace(go.Scatter(
                    x=t_interp, y=de_dt, mode='lines',
                    line=dict(color='#d62728', width=1.25),
                    opacity=0.9, showlegend=False,
                ), secondary_y=True)

                # 突跃点标记 —— 含假突跃判定
                dt_seg = np.diff(t_seg)
                # 找一阶导所有局部极小值，按导数值从小到大排序
                local_min_idx = argrelextrema(de_dt, np.less, order=2)[0]
                global_min_idx = np.argmin(de_dt)
                if global_min_idx not in local_min_idx:
                    local_min_idx = np.append(local_min_idx, global_min_idx)
                sorted_idx = local_min_idx[np.argsort(de_dt[local_min_idx])]

                false_jump_points = []
                t_jump = None
                de_jump = None

                for cand_idx in sorted_idx:
                    t_cand = t_interp[cand_idx]
                    orig_idx = int(np.clip(
                        np.searchsorted(t_seg, t_cand), 1, len(t_seg) - 2))
                    is_false = False

                    if np.isclose(t_cand, t_seg[orig_idx]):
                        # 候选点落在散点上 → 检查该散点及其 ±1 相邻散点
                        for offset in (-1, 0, 1):
                            oi = orig_idx + offset
                            if oi < 1 or oi >= len(t_seg) - 1:
                                continue
                            before = t_seg[oi] - t_seg[oi - 1]
                            after = t_seg[oi + 1] - t_seg[oi]
                            if not np.isclose(before, after):
                                is_false = True
                                break
                    else:
                        # 候选点落在两个散点之间 → 只检查这两个散点
                        for bi in (orig_idx - 1, orig_idx):
                            if bi < 1 or bi >= len(t_seg) - 1:
                                continue
                            before = t_seg[bi] - t_seg[bi - 1]
                            after = t_seg[bi + 1] - t_seg[bi]
                            if not np.isclose(before, after):
                                is_false = True
                                break

                    if is_false:
                        false_jump_points.append((t_cand, de_dt[cand_idx]))
                        continue

                    t_jump = t_cand
                    de_jump = de_dt[cand_idx]
                    break

                if t_jump is None:
                    min_idx = np.argmin(de_dt)
                    t_jump = t_interp[min_idx]
                    de_jump = de_dt[min_idx]

                jump_points.append(t_jump)

                if false_jump_points:
                    print(f"  - 警告：第 {i+1} 段曲线检测到 {len(false_jump_points)} 处"
                          f"假突跃（由测量时间间隔切换引起）：")
                    for fi, (tf, df) in enumerate(false_jump_points):
                        print(f"    假突跃 {fi+1}: t = {tf:.1f} s, "
                              f"dE/dt = {df:.1f} mV/s")
                    print(f"    已自动排除，采用真突跃点: t = {t_jump:.1f} s")

                # 真突跃点标记（红色三角）
                fig.add_trace(go.Scatter(
                    x=[t_jump], y=[de_jump], mode='markers',
                    marker=dict(color='#d62728', symbol='triangle-up', size=8),
                    showlegend=False,
                ), secondary_y=True)

                # 灰色虚线投影到横轴
                fig.add_vline(x=t_jump, line=dict(color='gray', dash='dash',
                                                  width=1),
                              opacity=0.6)

                # 横轴下方标注时间
                fig.add_annotation(
                    x=t_jump, y=-0.04, xref='x', yref='paper',
                    text=f'{t_jump:.1f}', showarrow=False,
                    font=dict(size=13, color='black', family=_SANS_FONT),
                    textangle=-90, yanchor='top',
                )

                # 假突跃标记（橙色空心圆圈 + 文字说明）
                for tf, df in false_jump_points:
                    fig.add_trace(go.Scatter(
                        x=[tf], y=[df], mode='markers',
                        marker=dict(color='orange', symbol='circle-open',
                                    size=10, line=dict(width=2)),
                        showlegend=False,
                    ), secondary_y=True)

                    fig.add_annotation(
                        x=tf, y=df, xref='x', yref='y2',
                        text='假突跃', showarrow=True,
                        arrowhead=2, arrowcolor='orange', arrowwidth=1.5,
                        ax=25, ay=-35,
                        font=dict(color='#cc7000', size=11,
                                  family=_SANS_FONT),
                        bgcolor='rgba(255,255,255,0.85)',
                        borderpad=3,
                    )

            last_t = t_seg[-1]
            last_E = e_smooth[-1]

        fig.update_yaxes(
            title_text="d<i>E</i>/d<i>t</i> / mV·s<sup>-1</sup>",
            title_font=dict(color='#d62728', **_ax_title),
            tickfont=dict(color='#d62728', size=13),
            secondary_y=True, **_ax_line,
        )

        default_title = f"Coulomb Titration Curve ({os.path.splitext(os.path.basename(path))[0]})"
        print("提示：图片标题/图例支持用 _ ^ {} 表示化学式（文件名不支持），例如 SO_4^{2-} 表示 SO₄²⁻")
        title_raw = input(f"请输入图片标题（敲下 Enter 则采用默认标题「{default_title}」): ").strip()
        if not title_raw:
            title_raw = default_title
        title_final = _format_sub_sup(title_raw)

        _has_jump_info = len(jump_points) > 1

        fig.update_layout(
            title=dict(text=title_final, font=dict(family=_SANS_FONT, size=18),
                       x=0.5, xanchor='center', y=0.94, yanchor='bottom'),
            font=dict(family=_SANS_FONT, size=13),
            xaxis=dict(title=dict(text="",
                                  standoff=5),
                       tickfont=dict(family=_SANS_FONT, size=13)),
            yaxis=dict(title=dict(text="<i>E</i> / mV",
                                  font=dict(family=_SANS_FONT, **_ax_title),
                                  standoff=2),
                       tickfont=dict(family=_SANS_FONT, size=13)),
            yaxis2=dict(title=dict(font=dict(family=_SANS_FONT, **_ax_title),
                                  standoff=12),
                        tickfont=dict(family=_SANS_FONT, size=13)),
            legend=dict(x=0.90, y=0.97, xanchor='right', yanchor='top',
                        bgcolor='rgba(255,255,255,0.2)',
                        bordercolor='black', borderwidth=1),
            template='plotly_white',
            width=fig_width, height=fig_height,
            margin=dict(l=70, r=20, t=40, b=60),
        )

        # 横轴标签用 annotation 实现，支持与突跃点标注避让
        _xlabel_x = 0.5
        if jump_points:
            _t_min, _t_max = times.min(), times.max()
            _t_range = _t_max - _t_min
            if _t_range > 0:
                for _tj in jump_points:
                    _norm = (_tj - _t_min) / _t_range
                    if abs(_norm - 0.5) < 0.02:
                        _xlabel_x = 0.55 if _norm <= 0.5 else 0.45
                        break
        fig.add_annotation(
            x=_xlabel_x, y=-0.06, xref='paper', yref='paper',
            text="<i>t</i> / s", showarrow=False,
            font=dict(family=_SANS_FONT, **_ax_title),
            xanchor='center', yanchor='top',
        )

        # 突跃点时间间隔放在图内左下角，字号与坐标轴标题一致，离下轴稍远
        if _has_jump_info:
            intervals = np.diff(jump_points)
            items = []
            for idx, interval in enumerate(intervals):
                items.append(f"第{idx+1}次与第{idx+2}次: {interval:.1f} s")
            info_str = "（突跃点时间间隔）   " + "      ".join(items)

            fig.add_annotation(
                x=0.01, y=0.03, xref='paper', yref='paper',
                text=info_str, showarrow=False,
                font=dict(family=_SERIF_FONT, size=15),
                xanchor='left', yanchor='bottom',
            )

        # 图例（右上角，图内，不覆盖曲线）
        if _prompt_yes_no("是否需要添加图例？(Y/n): "):
            default_legend = os.path.splitext(os.path.basename(path))[0]
            legend_raw = input(f"请输入图例名称（敲下 Enter 则采用默认名称「{default_legend}」): ").strip()
            if not legend_raw:
                legend_raw = default_legend
            legend_name = _format_sub_sup(legend_raw)
            fig.add_trace(go.Scatter(
                x=[None], y=[None], mode='lines',
                line=dict(color='#1f77b4', width=2.5),
                name=legend_name, showlegend=True,
            ), secondary_y=False)
            # 横轴向右延长以容纳图例
            _x_range = fig.layout.xaxis.range
            if _x_range:
                fig.update_xaxes(range=[_x_range[0],
                                        _x_range[1] + (_x_range[1] - _x_range[0]) * 0.08])

        png_path = _safe_save_path(os.path.splitext(path)[0] + '.png')
        try:
            fig.write_image(png_path, scale=3)
            print(f"图像已保存至: {png_path}")
        except Exception as e:
            print(f"保存图像失败: {e}\n"
                  "请确认已安装 kaleido: pip install kaleido", file=sys.stderr)


def contrast_plot(csv_paths, show_dots=False):
    """Overlay multiple CSV files on a single plot with smoothed fitting curves.

    Each CSV may contain one or more parallel curves (detected by potential
    jumps > 100 mV).  The user selects which curve to use per file and
    provides a legend name.  No derivative curves or
    jump-time annotations are drawn.
    """
    if not HAS_LIBS:
        print("缺少绘图需要的 numpy, scipy, plotly 库，不能绘图。"
              "请使用 pip install numpy scipy plotly kaleido 安装。")
        return

    _check_cjk_fonts()

    selected_data = []
    _first_prompt = True

    for path in csv_paths:
        if os.path.isdir(path):
            print(f"不支持的文件类型: {path}（文件夹）")
            continue
        if not path.endswith('.csv'):
            if path.endswith('.dat'):
                print(f"{path} 是 .dat 文件，请先通过 -e 将其转换为 CSV 格式。")
            else:
                print(f"不支持的文件类型: {path}")
            continue
        if not os.path.exists(path):
            print(f"文件不存在: {path}。请确保文件存在，并且处于正确的路径中。", file=sys.stderr)
            continue

        try:
            data = np.loadtxt(path, delimiter=',', skiprows=1)
        except FileNotFoundError:
            print(f"文件不存在: {path}。请确保文件存在，并且处于正确的路径中。", file=sys.stderr)
            continue
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
        if _first_prompt:
            print("提示：图片标题/图例支持用 _ ^ {} 表示化学式（文件名不支持），例如 SO_4^{2-} 表示 SO₄²⁻")
            _first_prompt = False
        legend_raw = input(f"请输入此曲线的图例名称 "
                           f"（敲下 Enter 则采用默认名称「{default_legend}」): ").strip()
        if not legend_raw:
            legend_raw = default_legend
        legend_name = _format_sub_sup(legend_raw)

        seg = segments[choice]
        if len(seg) < 5:
            print(f"  - 警告：第 {choice+1} 段曲线数据点不足5个，跳过。")
            continue
        t_shifted = seg[:, 0] - seg[:, 0].min()
        selected_data.append((legend_name, t_shifted, seg[:, 1]))

    if len(selected_data) < 1:
        print("没有足够的数据可供绘图。")
        return

    fig = go.Figure()

    all_t_min, all_t_max = float('inf'), float('-inf')
    all_e_min, all_e_max = float('inf'), float('-inf')

    for i, (name, t_seg, e_seg) in enumerate(selected_data):
        color = _CONTRAST_COLORS[i % len(_CONTRAST_COLORS)]
        marker = _MARKER_MAP.get(_MARKERS[i % len(_MARKERS)], 'circle')

        if len(e_seg) < 5:
            continue

        if len(np.unique(t_seg)) != len(t_seg):
            print(f"  - 警告：{name} 的时间列中存在重复值"
                  f"（同一时间对应多个电位数据），曲线可能显示异常。")

        e_smooth = savgol_filter(e_seg, window_length=5, polyorder=2)

        if show_dots:
            fig.add_trace(go.Scatter(
                x=t_seg, y=e_seg, mode='markers',
                marker=dict(color=color, symbol=marker, size=4,
                            line=dict(width=0.5, color=color)),
                opacity=0.8, showlegend=False,
            ))
            fig.add_trace(go.Scatter(
                x=t_seg, y=e_smooth, mode='lines',
                line=dict(color=color, width=2.5),
                name=name, showlegend=True,
            ))
        else:
            fig.add_trace(go.Scatter(
                x=t_seg, y=e_smooth, mode='lines',
                line=dict(color=color, width=2.5),
                name=name, showlegend=True,
            ))

        all_t_min = min(all_t_min, t_seg.min())
        all_t_max = max(all_t_max, t_seg.max())
        all_e_min = min(all_e_min, e_seg.min(), e_smooth.min())
        all_e_max = max(all_e_max, e_seg.max(), e_smooth.max())

    x_margin = max(35, (all_t_max - all_t_min) * 0.12)
    e_pad = (all_e_max - all_e_min) * 0.08

    # Closed black axis box
    _ax_line = dict(showline=True, linewidth=1.25, linecolor='black',
                    mirror=True, ticks='inside')
    _ax_title = dict(size=15)

    fig.update_xaxes(range=[all_t_min - 5, all_t_max + x_margin], **_ax_line)
    fig.update_yaxes(range=[all_e_min - e_pad, all_e_max + e_pad], **_ax_line)

    default_title = "Contrast Overlay"
    title_raw = input(f"请输入图片标题（敲下 Enter 则采用默认标题「{default_title}」): ").strip()
    if not title_raw:
        title_raw = default_title

    fig.update_layout(
        title=dict(text=_format_sub_sup(title_raw),
                   font=dict(family=_SANS_FONT, size=18), x=0.5, xanchor='center',
                   y=0.94, yanchor='bottom'),
        font=dict(family=_SANS_FONT, size=13),
        xaxis=dict(title=dict(text="<i>t</i> / s",
                              font=dict(family=_SANS_FONT, **_ax_title),
                              standoff=5),
                   tickfont=dict(family=_SANS_FONT, size=13)),
        yaxis=dict(title=dict(text="<i>E</i> / mV",
                              font=dict(family=_SANS_FONT, **_ax_title),
                              standoff=2),
                   tickfont=dict(family=_SANS_FONT, size=13)),
        legend=dict(x=0.94, y=0.97, xanchor='right', yanchor='top',
                    bgcolor='rgba(255,255,255,0.2)',
                    bordercolor='black', borderwidth=1),
        template='plotly_white',
        width=600, height=600,
        margin=dict(l=70, r=20, t=40, b=50),
    )

    while True:
        filename = input("请输入保存文件名: ").strip()
        if filename:
            break
        print("名称不能为空，请重新输入。")
    if not filename.lower().endswith('.png'):
        filename += '.png'
    filename = _safe_save_path(filename)
    try:
        fig.write_image(filename, scale=3)
        print(f"\n对比图已保存至: {filename}")
    except Exception as e:
        print(f"保存图像失败: {e}\n"
              "请确认已安装 kaleido: pip install kaleido", file=sys.stderr)


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
                    try:
                        _dir_entries = os.listdir(path)
                    except FileNotFoundError:
                        print(f"文件夹不存在: {path}。请确保文件夹存在，并且处于正确的路径中。", file=sys.stderr)
                        continue
                    existing = sorted([
                        os.path.join(path, f) for f in _dir_entries
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
        all_csvs = []
        csv_set = set()

        def _collect_csv(p):
            if os.path.isdir(p):
                try:
                    _entries = os.listdir(p)
                except FileNotFoundError:
                    print(f"文件夹不存在: {p}。请确保文件夹存在，并且处于正确的路径中。", file=sys.stderr)
                    return
                for f in sorted(_entries):
                    fp = os.path.join(p, f)
                    if os.path.isfile(fp):
                        _collect_csv(fp)
                return
            if not os.path.exists(p):
                print(f"文件不存在: {p}。请确保文件存在，并且处于正确的路径中。", file=sys.stderr)
                return
            if p.endswith('.csv'):
                real = os.path.realpath(p)
                if real not in csv_set:
                    all_csvs.append(p)
                    csv_set.add(real)
            elif p.endswith('.dat'):
                csv_path = p[:-4] + '.csv'
                if os.path.exists(csv_path):
                    real = os.path.realpath(csv_path)
                    if real not in csv_set:
                        all_csvs.append(csv_path)
                        csv_set.add(real)
                else:
                    print(f"{p} 是 .dat 文件，请先通过 -e 将其转换为 CSV 格式。")
            else:
                print(f"不支持的文件类型: {p}")

        for p in args.contrast:
            _collect_csv(p)

        if len(all_csvs) < 2:
            print("可供对比的 CSV 文件不足 2 个，无法绘制对比图。")
        else:
            contrast_plot(all_csvs, show_dots=show_dots)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
