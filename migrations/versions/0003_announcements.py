import sqlalchemy as sa
from alembic import op

revision = "0003_announcements"
down_revision = "0002_prediction_submission_time"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "announcements",
        sa.Column("match_id", sa.Integer(), nullable=False),
        sa.Column("announcement_type", sa.String(length=40), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"]),
        sa.PrimaryKeyConstraint("match_id", "announcement_type"),
    )


def downgrade() -> None:
    op.drop_table("announcements")
