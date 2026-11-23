from setuptools import find_packages, setup


# Increment the version every upload
setup(
    name="sqlalchemy-materialize",
    version="0.1.4",
    packages=find_packages(),
    install_requires=["SQLAlchemy>=2.0,<2.1", "psycopg2-binary>=2.9.13"],
    entry_points={
        "sqlalchemy.dialects": [
            "materialize.psycopg2 = "
            "sqlalchemy_materialize.psycopg2:MaterializeDialect_psycopg2",
        ],
    },
)