"""Baseline: DATABASE_CONTRACT v1.0.0 schema with the v1.1.0 tool_used values.

Revision ID: 0001
Revises:
Create Date: 2026-11-01
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

TOOL_USED = (
    "'rsunivlm_vqa', 'rsunivlm_cap', 'rsunivlm_vg', 'rsunivlm_seg', 'rsunivlm_ccd', "
    "'qwen_vl_vqa', 'qwen_vl_cap', 'qwen_vl_vg', 'qwen_vl_seg', 'qwen_vl_ccd', 'fusion_classifier'"
)


def upgrade() -> None:
    op.create_table(
        "images",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("modality", sa.Text, nullable=False),
        sa.Column("capture_date", sa.Text),
        sa.Column("storage_path", sa.Text, nullable=False),
        sa.Column("checksum", sa.Text, nullable=False),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.CheckConstraint("modality IN ('optical', 'sar')", name="ck_images_modality"),
    )
    op.create_table(
        "queries",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("query_text", sa.Text, nullable=False),
        sa.Column("image_ids", sa.Text, nullable=False),
        sa.Column("selected_task", sa.Text, nullable=False),
        sa.Column("tool_used", sa.Text, nullable=False),
        sa.Column("parameters", sa.Text),
        sa.Column("answer", sa.Text),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("visual_evidence_type", sa.Text, nullable=False),
        sa.Column("visual_evidence_ref", sa.Text),
        sa.Column("latency_ms", sa.Integer, nullable=False),
        sa.Column("inputs_validated", sa.Integer, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("error_code", sa.Text),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.CheckConstraint(
            "selected_task IN ('vqa', 'captioning', 'detection', 'change_detection', 'fusion')",
            name="ck_queries_selected_task"),
        sa.CheckConstraint(f"tool_used IN ({TOOL_USED})", name="ck_queries_tool_used"),
        sa.CheckConstraint("visual_evidence_type IN ('none', 'bbox', 'mask')", name="ck_queries_ve_type"),
        sa.CheckConstraint("inputs_validated IN (0, 1)", name="ck_queries_inputs_validated"),
        sa.CheckConstraint("status IN ('success', 'error')", name="ck_queries_status"),
    )


def downgrade() -> None:
    op.drop_table("queries")
    op.drop_table("images")
