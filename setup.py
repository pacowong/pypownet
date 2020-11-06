import setuptools

with open("README.md", "r") as fh:
    long_description = "\n".join(fh.readlines())

setuptools.setup(
    name="pypownetr",
    version="0.1.0",
    author="pacowong",
    author_email="",
    description="Chowdhury et al. PowNet Refactored",
    long_description=long_description,
    url="https://github.com/pacowong/pypownet",
    packages=setuptools.find_packages(),
    package_data={'pypownet': ['datasets/kamal0013/camb_2016/*.csv']
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
    install_requires=['pyomo', 'pandas'],
)