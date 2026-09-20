import sqlalchemy as sa
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "matches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("guild_id", sa.Integer(), nullable=False),
        sa.Column("home_team", sa.String(length=120), nullable=False),
        sa.Column("away_team", sa.String(length=120), nullable=False),
        sa.Column("competition", sa.String(length=120), nullable=False),
        sa.Column("kickoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("final_home_score", sa.Integer(), nullable=True),
        sa.Column("final_away_score", sa.Integer(), nullable=True),
    )
    op.create_index("ix_matches_guild_id", "matches", ["guild_id"])
    op.create_index("ix_matches_kickoff_at", "matches", ["kickoff_at"])
    op.create_table(
        "predictions",
        sa.Column("match_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("home_score", sa.Integer(), nullable=False),
        sa.Column("away_score", sa.Integer(), nullable=False),
        sa.Column("points", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"]),
        sa.PrimaryKeyConstraint("match_id", "user_id"),
    )


def downgrade() -> None:
    op.drop_table("predictions")
    op.drop_index("ix_matches_kickoff_at", table_name="matches")
    op.drop_index("ix_matches_guild_id", table_name="matches")
    op.drop_table("matches")
