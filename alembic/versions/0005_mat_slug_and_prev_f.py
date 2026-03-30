"""material slug and preview fields"""

import re
import unicodedata

import sqlalchemy as sa
from alembic import op


revision = "0005_mat_slug_and_prev_f"
down_revision = "0004_refresh_token_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("materials", sa.Column("slug", sa.String(length=255), nullable=True))
    op.add_column("material_files", sa.Column("preview_storage_key", sa.String(length=512), nullable=True))
    op.add_column("material_files", sa.Column("preview_page_count", sa.Integer(), nullable=True))

    bind = op.get_bind()
    materials = sa.table(
        "materials",
        sa.column("id", sa.String(length=36)),
        sa.column("title", sa.String(length=255)),
        sa.column("slug", sa.String(length=255)),
    )

    rows = bind.execute(sa.select(materials.c.id, materials.c.title).order_by(materials.c.id)).fetchall()
    used_slugs: set[str] = set()
    for row in rows:
        base_slug = _slugify(row.title or "material")
        slug = base_slug
        suffix = 2
        while slug in used_slugs:
            slug = f"{base_slug}-{suffix}"
            suffix += 1
        used_slugs.add(slug)
        bind.execute(
            materials.update()
            .where(materials.c.id == row.id)
            .values(slug=slug)
        )

    op.alter_column("materials", "slug", existing_type=sa.String(length=255), nullable=False)
    op.create_index(op.f("ix_materials_slug"), "materials", ["slug"], unique=True)
    op.create_unique_constraint("uq_material_files_preview_storage_key", "material_files", ["preview_storage_key"])


def downgrade() -> None:
    op.drop_constraint("uq_material_files_preview_storage_key", "material_files", type_="unique")
    op.drop_index(op.f("ix_materials_slug"), table_name="materials")
    op.drop_column("material_files", "preview_page_count")
    op.drop_column("material_files", "preview_storage_key")
    op.drop_column("materials", "slug")


def _slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", normalized).strip("-").lower()
    return normalized or "material"
