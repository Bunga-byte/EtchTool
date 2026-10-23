from alembic import context
from sqlalchemy import create_engine
from app.models import Base
import app.enterprise.models  # register additive enterprise metadata
from app.config import settings

config = context.config


def configure(connection):
    context.configure(
        connection=connection, target_metadata=Base.metadata, compare_type=True
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    context.configure(
        url=settings().database_url, target_metadata=Base.metadata, literal_binds=True
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    provided = config.attributes.get("connection")
    if provided is not None:
        configure(provided)
    else:
        with create_engine(settings().database_url).connect() as connection:
            configure(connection)
