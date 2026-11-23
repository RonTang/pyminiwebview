from pathlib import Path
import re

from setuptools import Extension, setup


def project_version():
    pyproject = (Path(__file__).parent / "pyproject.toml").read_text(
        encoding="utf-8"
    )
    match = re.search(r'(?m)^version = "([^"]+)"$', pyproject)
    if match is None:
        raise RuntimeError("Project version is missing from pyproject.toml")
    return match.group(1)


setup(
    ext_modules=[
        Extension(
            "pyminiwebview",
            sources=["src/pyminiwebview/_module.cpp"],
            depends=[
                "src/pyminiwebview/_composition.h",
                "vendor/webview/webview.h",
            ],
            include_dirs=["vendor"],
            language="c++",
            define_macros=[
                ("Py_LIMITED_API", "0x03090000"),
                ("PYMINIWEBVIEW_VERSION", f'"{project_version()}"'),
            ],
            py_limited_api=True,
            extra_compile_args=["/std:c++14", "/EHsc", "/W3"],
            libraries=["comctl32", "dcomp"],
        )
    ]
)
