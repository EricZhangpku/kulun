import os
from setuptools import setup

# 读取 README.md 作为长描述
long_description = ""
if os.path.exists("README.md"):
    with open("README.md", "r", encoding="utf-8") as fh:
        long_description = fh.read()

setup(
    name="kulun",  # 包名，你在 pip install 时候的名字
    version="1.0.0", # 版本号
    author="张嘉航", # 作者名称
    author_email="2062605586@qq.com", # 作者邮箱
    description="A CLI tool to process and plot Coulomb titration .dat files",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/EricZhangpku/kulun", # 项目主页
    # 如果只有单个脚本文件 kulun.py，可以使用 py_modules
    py_modules=["kulun"],
    install_requires=[
        "numpy",
        "scipy",
        "matplotlib"
    ],
    # 核心：将命令行中的 "kulun" 指令映射到 kulun.py 的 main() 函数
    entry_points={
        "console_scripts": [
            "kulun = kulun:main",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.6",
)
