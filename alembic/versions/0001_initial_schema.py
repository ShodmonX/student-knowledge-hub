"""initial schema"""

from alembic import op
import sqlalchemy as sa


revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    user_role = sa.Enum("STUDENT", "MODERATOR", "ADMIN", name="userrole")
    material_status = sa.Enum("DRAFT", "PENDING_REVIEW", "APPROVED", "REJECTED", name="materialstatus")
    material_type = sa.Enum(
        "BOOK", "NOTES", "SLIDES", "EXAM", "ASSIGNMENT", "LAB", "CHEATSHEET", "OTHER", name="materialtype"
    )
    reject_reason = sa.Enum(
        "WRONG_SUBJECT",
        "DUPLICATE",
        "UNREADABLE",
        "LOW_QUALITY",
        "SPAM",
        "COPYRIGHT_OR_POLICY_ISSUE",
        "OTHER",
        name="rejectreason",
    )
    file_kind = sa.Enum("IMAGE", "DOCUMENT", "ARCHIVE", "OTHER", name="filekind")
    review_action = sa.Enum(
        "SUBMITTED",
        "APPROVED",
        "REJECTED",
        "RESUBMITTED",
        "MOVED_SUBJECT",
        "WITHDRAWN",
        "REPORTED",
        "TAKEDOWN",
        name="reviewaction",
    )

    bind = op.get_bind()
    user_role.create(bind, checkfirst=True)
    material_status.create(bind, checkfirst=True)
    material_type.create(bind, checkfirst=True)
    reject_reason.create(bind, checkfirst=True)
    file_kind.create(bind, checkfirst=True)
    review_action.create(bind, checkfirst=True)

    op.create_table(
        "universities",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_universities_slug"), "universities", ["slug"], unique=True)

    op.create_table(
        "users",
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("role", user_role, nullable=False),
        sa.Column("university_id", sa.String(length=36), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_verified", sa.Boolean(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["university_id"], ["universities.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_index(op.f("ix_users_university_id"), "users", ["university_id"], unique=False)

    op.create_table(
        "faculties",
        sa.Column("university_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["university_id"], ["universities.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("university_id", "slug", name="uq_faculty_university_slug"),
    )
    op.create_index(op.f("ix_faculties_university_id"), "faculties", ["university_id"], unique=False)

    op.create_table(
        "subjects",
        sa.Column("faculty_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=True),
        sa.Column("semester", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["faculty_id"], ["faculties.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("faculty_id", "slug", "semester", name="uq_subject_faculty_slug_semester"),
    )
    op.create_index(op.f("ix_subjects_faculty_id"), "subjects", ["faculty_id"], unique=False)

    op.create_table(
        "tags",
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("slug"),
    )

    op.create_table(
        "materials",
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("material_type", material_type, nullable=False),
        sa.Column("status", material_status, nullable=False),
        sa.Column("subject_id", sa.String(length=36), nullable=False),
        sa.Column("uploaded_by", sa.String(length=36), nullable=False),
        sa.Column("approved_by", sa.String(length=36), nullable=True),
        sa.Column("last_reviewed_by", sa.String(length=36), nullable=True),
        sa.Column("rejected_reason", reject_reason, nullable=True),
        sa.Column("cover_file_id", sa.String(length=36), nullable=True),
        sa.Column("primary_file_id", sa.String(length=36), nullable=True),
        sa.Column("file_count", sa.Integer(), nullable=False),
        sa.Column("total_size", sa.Integer(), nullable=False),
        sa.Column("download_count", sa.Integer(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["last_reviewed_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["subject_id"], ["subjects.id"]),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_materials_created_at"), "materials", ["created_at"], unique=False)
    op.create_index(op.f("ix_materials_material_type"), "materials", ["material_type"], unique=False)
    op.create_index(op.f("ix_materials_status"), "materials", ["status"], unique=False)
    op.create_index(op.f("ix_materials_subject_id"), "materials", ["subject_id"], unique=False)
    op.create_index(op.f("ix_materials_uploaded_by"), "materials", ["uploaded_by"], unique=False)

    op.create_table(
        "material_files",
        sa.Column("material_id", sa.String(length=36), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("file_ext", sa.String(length=32), nullable=False),
        sa.Column("file_kind", file_kind, nullable=False),
        sa.Column("file_order", sa.Integer(), nullable=False),
        sa.Column("checksum_hash", sa.String(length=64), nullable=False),
        sa.Column("is_previewable", sa.Boolean(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index(op.f("ix_material_files_checksum_hash"), "material_files", ["checksum_hash"], unique=False)
    op.create_index(op.f("ix_material_files_file_kind"), "material_files", ["file_kind"], unique=False)
    op.create_index(op.f("ix_material_files_material_id"), "material_files", ["material_id"], unique=False)

    op.create_foreign_key("fk_material_cover_file", "materials", "material_files", ["cover_file_id"], ["id"])
    op.create_foreign_key("fk_material_primary_file", "materials", "material_files", ["primary_file_id"], ["id"])

    op.create_table(
        "material_tags",
        sa.Column("material_id", sa.String(length=36), nullable=False),
        sa.Column("tag_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"]),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"]),
        sa.PrimaryKeyConstraint("material_id", "tag_id"),
    )

    op.create_table(
        "material_review_logs",
        sa.Column("material_id", sa.String(length=36), nullable=False),
        sa.Column("action", review_action, nullable=False),
        sa.Column("actor_id", sa.String(length=36), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("reason", sa.String(length=128), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_material_review_logs_actor_id"), "material_review_logs", ["actor_id"], unique=False)
    op.create_index(op.f("ix_material_review_logs_material_id"), "material_review_logs", ["material_id"], unique=False)

    op.create_table(
        "moderator_university_scopes",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("university_id", sa.String(length=36), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["university_id"], ["universities.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "university_id", name="uq_mod_uni_scope"),
    )
    op.create_index(op.f("ix_moderator_university_scopes_university_id"), "moderator_university_scopes", ["university_id"], unique=False)
    op.create_index(op.f("ix_moderator_university_scopes_user_id"), "moderator_university_scopes", ["user_id"], unique=False)

    op.create_table(
        "moderator_faculty_scopes",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("faculty_id", sa.String(length=36), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["faculty_id"], ["faculties.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "faculty_id", name="uq_mod_fac_scope"),
    )
    op.create_index(op.f("ix_moderator_faculty_scopes_faculty_id"), "moderator_faculty_scopes", ["faculty_id"], unique=False)
    op.create_index(op.f("ix_moderator_faculty_scopes_user_id"), "moderator_faculty_scopes", ["user_id"], unique=False)

    op.create_table(
        "moderator_subject_scopes",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("subject_id", sa.String(length=36), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["subject_id"], ["subjects.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "subject_id", name="uq_mod_sub_scope"),
    )
    op.create_index(op.f("ix_moderator_subject_scopes_subject_id"), "moderator_subject_scopes", ["subject_id"], unique=False)
    op.create_index(op.f("ix_moderator_subject_scopes_user_id"), "moderator_subject_scopes", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_table("moderator_subject_scopes")
    op.drop_table("moderator_faculty_scopes")
    op.drop_table("moderator_university_scopes")
    op.drop_table("material_review_logs")
    op.drop_table("material_tags")
    op.drop_constraint("fk_material_primary_file", "materials", type_="foreignkey")
    op.drop_constraint("fk_material_cover_file", "materials", type_="foreignkey")
    op.drop_table("material_files")
    op.drop_table("materials")
    op.drop_table("tags")
    op.drop_table("subjects")
    op.drop_table("faculties")
    op.drop_table("users")
    op.drop_table("universities")
