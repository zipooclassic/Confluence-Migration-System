from setuptools import setup, find_packages

setup(
    name='confluence-migration-system',
    version='0.1.0',
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        'Flask',
        'atlassian-python-api',
        'SQLAlchemy',
        'python-dotenv',
        'gunicorn',
    ],
    entry_points={
        'console_scripts': [
            'confluence-migration=main:main',
        ],
    },
)
