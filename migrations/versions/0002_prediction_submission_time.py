import sqlalchemy as sa
from alembic import op

revision = "0002_prediction_submission_time"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "predictions",
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute("UPDATE predictions SET submitted_at = updated_at WHERE submitted_at IS NULL")


def downgrade() -> None:
    op.drop_column("predictions", "submitted_at")
