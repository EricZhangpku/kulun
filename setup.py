import os
from setuptools import setup

long_description = ""
if os.path.exists("README.md"):
    with open("README.md", "r", encoding="utf-8") as fh:
        long_description = fh.read()

setup(
    name="kulun",
    version="2.2.0",
    license="MIT",
    author="Jiahang Zhang",
    author_email="2062605586@qq.com",
    description="Coulomb titration .dat data processing and scientific plotting CLI tool",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/EricZhangpku/kulun",
    project_urls={
        "Bug Tracker": "https://github.com/EricZhangpku/kulun/issues",
        "Source": "https://github.com/EricZhangpku/kulun",
    },
    py_modules=["kulun"],
    install_requires=[
        "numpy",
        "scipy",
        "plotly",
        "kaleido",
    ],
    entry_points={
        "console_scripts": [
            "kulun = kulun:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Scientific/Engineering :: Chemistry",
        "Topic :: Scientific/Engineering :: Visualization",
    ],
    python_requires=">=3.7",
)
