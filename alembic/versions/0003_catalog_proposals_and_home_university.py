"""catalog proposals and home university cooldown"""

from alembic import op
import sqlalchemy as sa


revision = "0003_catalog_proposals_and_home_university"
down_revision = "0002_frontend_gap_features"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    proposal_status = sa.Enum("PENDING", "APPROVED", "REJECTED", name="proposalstatus")
    proposal_entity_type = sa.Enum(
        "UNIVERSITY", "FACULTY", "SUBJECT", name="proposalentitytype"
    )
    proposal_status.create(bind, checkfirst=True)
    proposal_entity_type.create(bind, checkfirst=True)

    op.add_column("users", sa.Column("university_changed_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "university_proposals",
        sa.Column("proposed_name", sa.String(length=255), nullable=False),
        sa.Column("proposed_slug", sa.String(length=255), nullable=True),
        sa.Column("proposed_description", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("status", proposal_status, nullable=False),
        sa.Column("reviewed_by", sa.String(length=36), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("approved_university_id", sa.String(length=36), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["approved_university_id"], ["universities.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_university_proposals_created_by"), "university_proposals", ["created_by"], unique=False)

    op.create_table(
        "faculty_proposals",
        sa.Column("university_id", sa.String(length=36), nullable=False),
        sa.Column("proposed_name", sa.String(length=255), nullable=False),
        sa.Column("proposed_slug", sa.String(length=255), nullable=True),
        sa.Column("proposed_description", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("status", proposal_status, nullable=False),
        sa.Column("reviewed_by", sa.String(length=36), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("approved_faculty_id", sa.String(length=36), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["approved_faculty_id"], ["faculties.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["university_id"], ["universities.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_faculty_proposals_created_by"), "faculty_proposals", ["created_by"], unique=False)
    op.create_index(op.f("ix_faculty_proposals_university_id"), "faculty_proposals", ["university_id"], unique=False)

    op.create_table(
        "subject_proposals",
        sa.Column("faculty_id", sa.String(length=36), nullable=False),
        sa.Column("proposed_name", sa.String(length=255), nullable=False),
        sa.Column("proposed_slug", sa.String(length=255), nullable=True),
        sa.Column("proposed_code", sa.String(length=64), nullable=True),
        sa.Column("proposed_semester", sa.Integer(), nullable=True),
        sa.Column("proposed_description", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("status", proposal_status, nullable=False),
        sa.Column("reviewed_by", sa.String(length=36), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("approved_subject_id", sa.String(length=36), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["approved_subject_id"], ["subjects.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["faculty_id"], ["faculties.id"]),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_subject_proposals_created_by"), "subject_proposals", ["created_by"], unique=False)
    op.create_index(op.f("ix_subject_proposals_faculty_id"), "subject_proposals", ["faculty_id"], unique=False)

    op.create_table(
        "catalog_proposal_logs",
        sa.Column("entity_type", proposal_entity_type, nullable=False),
        sa.Column("entity_id", sa.String(length=36), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("actor_id", sa.String(length=36), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_catalog_proposal_logs_actor_id"), "catalog_proposal_logs", ["actor_id"], unique=False)
    op.create_index(op.f("ix_catalog_proposal_logs_entity_id"), "catalog_proposal_logs", ["entity_id"], unique=False)
    op.create_index(op.f("ix_catalog_proposal_logs_entity_type"), "catalog_proposal_logs", ["entity_type"], unique=False)


def downgrade() -> None:
    op.drop_table("catalog_proposal_logs")
    op.drop_table("subject_proposals")
    op.drop_table("faculty_proposals")
    op.drop_table("university_proposals")
    op.drop_column("users", "university_changed_at")
