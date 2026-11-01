from setuptools import setup, find_packages

setup(
    name='codespeed',
    version='0.13.0+pythonspeed',
    author='Miquel Torres',
    author_email='tobami@gmail.com',
    url='https://github.com/tobami/codespeed',
    download_url="https://github.com/tobami/codespeed/tags",
    license='GNU Lesser General Public License version 2.1',
    keywords=['benchmarking', 'visualization'],
    python_requires='>=3.12',
    install_requires=['django>=5.2,<7', 'isodate', 'matplotlib'],
    packages=find_packages(exclude=['ez_setup', 'sample_project', 'speed_python']),
    setup_requires=['setuptools-markdown'],
    long_description_markdown_filename='README.md',
    description='A web application to monitor and analyze the performance of your code',
    include_package_data=True,
    zip_safe=False,
    classifiers=[
        'Environment :: Web Environment',
        'Framework :: Django',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: GNU Lesser General Public License v2 (LGPLv2)',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3 :: Only',
        'Programming Language :: Python :: 3.12',
        'Programming Language :: Python :: 3.13',
        'Programming Language :: Python :: 3.14',
        'Topic :: Internet :: WWW/HTTP :: WSGI :: Application',
    ]
)
