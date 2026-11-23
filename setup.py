from pathlib import Path

from setuptools import find_packages, setup


# Increment the version every upload
setup(
    name="sqlalchemy-materialize",
    version="0.1.4",
    description="A SQLAlchemy dialect for Materialize",
    long_description=Path(__file__).with_name("README.md").read_text(encoding="utf-8"),
    long_description_content_type="text/markdown",
    license="Apache-2.0",
    license_files=["LICENSE"],
    packages=find_packages(),
    install_requires=["SQLAlchemy>=2.0,<2.1", "psycopg2-binary>=2.9.13"],
    entry_points={
        "sqlalchemy.dialects": [
            "materialize.psycopg2 = "
            "sqlalchemy_materialize.psycopg2:MaterializeDialect_psycopg2",
        ],
    },
)
