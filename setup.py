from setuptools import find_packages, setup


setup(
    name="photo-utils",
    version="0.1.0",
    description="Local-first photo utilities",
    packages=find_packages(exclude=("tests", "tests.*")),
    python_requires=">=3.9",
    install_requires=[
        "numpy==2.0.2",
        "opencv-python-headless==4.11.0.86",
        "tifffile==2024.8.30",
    ],
    entry_points={
        "console_scripts": [
            "photo-utils=photo_utils.cli:main",
        ]
    },
)
