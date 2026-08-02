"""Give the trainer setup a home on the user row

The Phase 5 carryover. Phase 6 shipped ahead of Phase 5 and had no user row to
hang the trainer setup off, so it became a ``localStorage`` preference sent with
every request. This is the column it should always have had.

**Nullable, and not backfilled.** Three NULLs means "this account has never
chosen", which is deliberately distinct from "chose the defaults" — the first-run
dialog reads it, and backfilling today's defaults would freeze them into every
existing row. ``app.training.resolve_profile`` already falls back per absent
input, so a row of NULLs resolves to exactly the grading the app did before this
revision.

**No ``batch_alter_table``.** Adding a nullable column with no constraint and no
default is the one ``ALTER`` SQLite supports natively, so batch mode would rebuild
the table for nothing — and a rebuild is what revisions 0003 and 0005 had to
reason carefully about. Nothing here changes a type, so 0003's CAST trap is out
of range too.

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-01

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("user", sa.Column("experience", sa.Text(), nullable=True))
    op.add_column("user", sa.Column("sessions_per_week", sa.Integer(), nullable=True))
    op.add_column(
        "user", sa.Column("minutes_per_session", sa.Integer(), nullable=True)
    )


def downgrade() -> None:
    """Forget every account's trainer setup.

    Lossy, but only of a preference: a downgraded database grades every user
    against the baseline targets again, which is what the app did before Phase 6.
    """
    op.drop_column("user", "minutes_per_session")
    op.drop_column("user", "sessions_per_week")
    op.drop_column("user", "experience")
