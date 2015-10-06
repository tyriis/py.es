import os
from setuptools import setup

here = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(here, 'README.rst')) as f:
    README = f.read()

setup(
    name='score.es',
    version='0.1.7'
    description='ElasticSearch integration for The SCORE Framework',
    long_description=README,
    author='strg.at',
    author_email='score@strg.at',
    url='http://score-framework.org',
    keywords='score framework elasticsearch',
    packages=['score.es'],
    install_requires=[
        'elasticsearch >= 1.0, < 2.0',
    ]
)
