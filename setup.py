import codecs
import os
import re

from setuptools import Command, find_packages, setup

here = os.path.abspath(os.path.dirname(__file__))

version = '0.0.0'
changes = os.path.join(here, 'CHANGES.rst')
match = r'^#*\s*(?P<version>[0-9]+\.[0-9]+(\.[0-9]+)?)$'
with codecs.open(changes, encoding='utf-8') as changes:
    for line in changes:
        res = re.match(match, line)
        if res:
            version = res.group('version')
            break

# Get the long description
with codecs.open(os.path.join(here, 'README.rst'), encoding='utf-8') as f:
    long_description = f.read()

# Get version
with codecs.open(os.path.join(here, 'CHANGES.rst'), encoding='utf-8') as f:
    changelog = f.read()


install_requirements = []
tests_requirements = []


class VersionCommand(Command):
    description = 'print library version'
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        print(version)


if __name__ == '__main__':
    setup(
        name='crawl_config',
        description='Crawl config',
        version=version,
        long_description=long_description,
        long_description_content_type='text/x-rst',
        author='Daniel Bastos',
        author_email='danielfloresbastos@gmail.com',
        url='https://github.com/daniellbastos/crawl-config/',
        install_requires=install_requirements,
        tests_require=tests_requirements,
        keywords=['playwright'],
        packages=['crawl_config'],
        include_package_data=True,
        zip_safe=False,
        classifiers=[
            'Programming Language :: Python :: 3.10',
            'Topic :: Software Development :: Libraries',
        ],
        cmdclass={'version': VersionCommand},
    )
