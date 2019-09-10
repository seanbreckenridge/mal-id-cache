#!/usr/bin/env python

from setuptools import setup, find_packages

setup(
    author="Sean Breckenridge",
    author_email='seanbrecke@gmail.com',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: End Users/Desktop',
        'Natural Language :: English',
        'Programming Language :: Python :: 3',
    ],
    license="MIT",
    include_package_data=True,
    name='mal-id-cache',
    packages=find_packages(include=['mal_id_cache']),
    entry_points={
        'console_scripts': [
            "mal_id_cache = mal_id_cache.run:run_wrapper"
        ]
    },
    url='https://github.com/seanbreckenridge/mal-id-cache',
    version='0.1.0',
    zip_safe=False,
)

print("WARNING! The setup script does not install dependencies. That should be done through pipenv or requirements.txt")