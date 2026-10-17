"""photos, status timeline, encrypted contact, telegram, broad categories and responsible office

Revision ID: 7c1d2e3f4a5b
Revises: 503b37125ad8
Create Date: 2026-10-16 23:30:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "7c1d2e3f4a5b"
down_revision: Union[str, Sequence[str], None] = "503b37125ad8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_CHANNELS = "channel in ('phone', 'web', 'whatsapp')"
NEW_CHANNELS = "channel in ('phone', 'web', 'whatsapp', 'telegram')"


OLD_CATEGORIES = "('road', 'water', 'electricity', 'garbage', 'drainage', 'streetlight', 'other')"
NEW_CATEGORIES = ("('road', 'water', 'electricity', 'garbage', 'drainage', 'streetlight', 'trees', 'animals', "
                  "'noise', 'pollution', 'traffic', 'transport', 'health', 'education', 'ration', 'pension', "
                  "'safety', 'building', 'corruption', 'other')")
DEPARTMENTS = ("('bbmp', 'bescom', 'bwssb', 'bmtc', 'traffic_police', 'police', 'health', 'education', "
               "'food_civil_supplies', 'revenue', 'pollution_board', 'panchayat', 'lokayukta', 'unrouted')")


def upgrade() -> None:
    op.add_column("complaints", sa.Column("contact_enc", sa.Text(), nullable=True))
    op.add_column("complaints", sa.Column("department", sa.String(length=24), server_default="unrouted", nullable=False))
    op.add_column("complaints", sa.Column("sensitive", sa.Boolean(), server_default="false", nullable=False))
    op.create_check_constraint("ck_complaints_department", "complaints", f"department in {DEPARTMENTS}")
    op.drop_constraint("ck_complaints_category", "complaints", type_="check")
    op.create_check_constraint("ck_complaints_category", "complaints", f"category in {NEW_CATEGORIES}")
    # Existing complaints get their default office.
    for cat, dept in (("road", "bbmp"), ("garbage", "bbmp"), ("drainage", "bbmp"), ("streetlight", "bbmp"),
                      ("water", "bwssb"), ("electricity", "bescom")):
        op.execute(f"UPDATE complaints SET department = '{dept}' WHERE category = '{cat}'")
    op.drop_constraint("ck_complaints_channel", "complaints", type_="check")
    op.create_check_constraint("ck_complaints_channel", "complaints", NEW_CHANNELS)

    op.create_table(
        "photos",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("complaint_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("mime", sa.String(length=32), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("gemma_verdict", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("kind in ('citizen', 'fix')", name="ck_photos_kind"),
        sa.ForeignKeyConstraint(["complaint_id"], ["complaints.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_photos_complaint_id", "photos", ["complaint_id"])

    op.create_table(
        "status_changes",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("complaint_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("changed_by", sa.String(length=8), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status in ('open', 'in_progress', 'fixed', 'reopened')", name="ck_status_changes_status"),
        sa.CheckConstraint("changed_by in ('officer', 'citizen', 'system')", name="ck_status_changes_changed_by"),
        sa.ForeignKeyConstraint(["complaint_id"], ["complaints.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_status_changes_complaint_id", "status_changes", ["complaint_id"])

    # Same protection as every other table: Supabase's public API sees nothing.
    for table in ("photos", "status_changes"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_index("ix_status_changes_complaint_id", table_name="status_changes")
    op.drop_table("status_changes")
    op.drop_index("ix_photos_complaint_id", table_name="photos")
    op.drop_table("photos")
    op.drop_constraint("ck_complaints_channel", "complaints", type_="check")
    op.create_check_constraint("ck_complaints_channel", "complaints", OLD_CHANNELS)
    op.drop_constraint("ck_complaints_category", "complaints", type_="check")
    op.create_check_constraint("ck_complaints_category", "complaints", f"category in {OLD_CATEGORIES}")
    op.drop_constraint("ck_complaints_department", "complaints", type_="check")
    op.drop_column("complaints", "sensitive")
    op.drop_column("complaints", "department")
    op.drop_column("complaints", "contact_enc")
