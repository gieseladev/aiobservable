import setuptools

import aiobservable

with open("README.md", "r") as f:
    long_description = f.read()

setuptools.setup(
    name="aiobservable",
    version=aiobservable.__version__,
    author=aiobservable.__author__,
    author_email="team@giesela.dev",
    url="https://github.com/gieseladev/aiobservable",

    licence="MIT",
    long_description=long_description,
    long_description_content_type="text/markdown",

    packages=setuptools.find_packages(exclude=("docs", "tests")),

    python_requires="~=3.7",
)
