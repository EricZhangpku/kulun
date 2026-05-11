#!/usr/bin/env python3
import os
import sys
import csv
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
            files = [os.path.join(path, f) for f in os.listdir(path) if f.endswith('.dat')]
            files.sort()
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
    # 全局默认 sans-serif：拉丁字符用 Arial，中文用黑体
    plt.rcParams['font.sans-serif'] = ['Arial'] + heiti_fonts + ['sans-serif']
    plt.rcParams['font.family'] = 'sans-serif'
    plt.rcParams['axes.unicode_minus'] = False

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
                         ha='center', va='top', rotation=90, fontsize=10, fontfamily='Arial', clip_on=False)

            last_t = t_seg[-1]
            last_E = e_smooth[-1]

        ax1.set_xlabel('$t$ / s', fontname='Arial')
        ax1.set_ylabel('$E$ / mV', color='b', fontname='Arial')
        ax2.set_ylabel('d$E$/d$t$ / mV$\cdot$s$^{-1}$', color='r', fontname='Arial')
        
        ax1.tick_params(axis='y', labelcolor='b')
        ax2.tick_params(axis='y', labelcolor='r')
        
        plt.title(f"Coulomb Titration Curve ({os.path.basename(path)})", fontfamily=['Arial'] + heiti_fonts)
        
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
            fig.text(0.06, bottom_margin - 0.04, info_str, ha='left', va='bottom', fontsize=11,
                 fontfamily=['Times New Roman'] + songti_fonts)
        else:
            fig.tight_layout()
        
        png_path = os.path.splitext(path)[0] + '.png'
        plt.savefig(png_path, dpi=300)
        print(f"图像已保存至: {png_path}")
        plt.close(fig)

EPILOG = """
Examples:
  kulun -e data.dat                从单个 .dat 文件提取数据为 CSV
  kulun -e ./data_folder/          批量提取文件夹内所有 .dat 文件
  kulun -c a.csv b.csv             按顺序合并多个 CSV 文件
  kulun -ec a.dat b.dat            提取多个 .dat 并合并为单个 CSV
  kulun -p data.csv                绘制滴定曲线及一阶导分析图
  kulun -cp a.csv b.csv            合并 CSV 并生成合并后的分析图
  kulun -ecp a.dat b.dat           提取、合并、绘图，一步到位

Project home: https://github.com/EricZhangpku/kulun
"""


def main():
    parser = argparse.ArgumentParser(
        prog="kulun",
        description="库仑滴定 (Coulomb titration) .dat 数据处理与科研绘图工具。\n"
                    "支持提取、合并、一键绘制滴定曲线及一阶导数分析图。",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        '-V', '--version', action='version',
        version=f'kulun {__version__}',
        help="显示版本号并退出",
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
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
