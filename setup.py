# setup.py
from setuptools import find_packages, setup

setup(
    name="sqlalchemy-materialize",
    version="0.1.2",
    packages=find_packages(),
    install_requires=["SQLAlchemy>=2.0,<2.1", "psycopg2>=2.9"],
    entry_points={
        "sqlalchemy.dialects": [
            "materialize.psycopg2 = "
            "sqlalchemy_materialize.psycopg2:MaterializeDialect_psycopg2",
        ],
    },
)