from setuptools import Extension, setup

setup(
    ext_modules=[
        Extension(
            "pyminiwebview",
            sources=["src/pyminiwebview/_module.cpp"],
            include_dirs=["vendor"],
            language="c++",
            define_macros=[("Py_LIMITED_API", "0x03090000")],
            py_limited_api=True,
            extra_compile_args=["/std:c++14", "/EHsc", "/W3"],
            libraries=["comctl32"],
        )
    ]
)
