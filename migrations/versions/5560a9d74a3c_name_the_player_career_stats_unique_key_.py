"""Name the player_career_stats unique key by convention

The initial schema created this constraint without a name, so each server
named it: MySQL after the column, SQLite not at all. Only a server-assigned
name can differ from the metadata, so only MySQL has work to do here.

Revision ID: 5560a9d74a3c
Revises: 658616cf0c2b
Create Date: 2026-08-16 16:17:18.221051

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5560a9d74a3c"
down_revision: str | Sequence[str] | None = "658616cf0c2b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "mysql":
        return
    op.drop_index("player_name", table_name="player_career_stats")
    op.create_unique_constraint(
        "uq_player_career_stats_player_name", "player_career_stats", ["player_name"]
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "mysql":
        return
    op.drop_constraint(
        "uq_player_career_stats_player_name", "player_career_stats", type_="unique"
    )
    op.create_index("player_name", "player_career_stats", ["player_name"], unique=True)
