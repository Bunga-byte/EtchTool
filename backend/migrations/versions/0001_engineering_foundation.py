"""Frozen engineering foundation schema; synthetic data is seeded separately.

Revision ID: 0001
Revises: none

This revision deliberately contains explicit DDL and no application-model imports.
Changing models does not retroactively change an existing migration.
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('audit_logs',
    sa.Column('id', sa.String(length=80), nullable=False),
    sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
    sa.Column('actor', sa.String(length=160), nullable=False),
    sa.Column('role', sa.String(length=40), nullable=False),
    sa.Column('action', sa.String(length=120), nullable=False),
    sa.Column('entity_type', sa.String(length=80), nullable=False),
    sa.Column('entity_id', sa.String(length=120), nullable=False),
    sa.Column('detail', sa.JSON(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('component_definitions',
    sa.Column('id', sa.String(length=80), nullable=False),
    sa.Column('manufacturer', sa.String(length=160), nullable=False),
    sa.Column('part_number', sa.String(length=120), nullable=False),
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('category', sa.String(length=100), nullable=False),
    sa.Column('function', sa.Text(), nullable=False),
    sa.Column('revision', sa.String(length=40), nullable=False),
    sa.Column('exposure_dimension', sa.String(length=80), nullable=False),
    sa.Column('failure_mechanisms', sa.JSON(), nullable=False),
    sa.Column('supersedes_id', sa.String(length=80), nullable=True),
    sa.ForeignKeyConstraint(['supersedes_id'], ['component_definitions.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('part_number')
    )
    op.create_index(op.f('ix_component_definitions_supersedes_id'), 'component_definitions', ['supersedes_id'], unique=False)
    op.create_table('equipment_configurations',
    sa.Column('id', sa.String(length=80), nullable=False),
    sa.Column('family', sa.String(length=80), nullable=False),
    sa.Column('variant', sa.String(length=120), nullable=False),
    sa.Column('revision', sa.String(length=40), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('failure_modes',
    sa.Column('id', sa.String(length=80), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('mechanism', sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('ingestion_runs',
    sa.Column('id', sa.String(length=80), nullable=False),
    sa.Column('adapter_id', sa.String(length=120), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('status', sa.String(length=80), nullable=False),
    sa.Column('record_count', sa.Integer(), nullable=False),
    sa.Column('duplicate_count', sa.Integer(), nullable=False),
    sa.Column('errors', sa.JSON(), nullable=False),
    sa.Column('cursor', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('raw_source_records',
    sa.Column('id', sa.String(length=80), nullable=False),
    sa.Column('source', sa.String(length=120), nullable=False),
    sa.Column('source_id', sa.String(length=160), nullable=False),
    sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('effective_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('ingested_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.Column('fingerprint', sa.String(length=64), nullable=False),
    sa.Column('quality', sa.String(length=80), nullable=False),
    sa.Column('verification', sa.String(length=80), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('fingerprint')
    )
    op.create_index(op.f('ix_raw_source_records_source'), 'raw_source_records', ['source'], unique=False)
    op.create_index(op.f('ix_raw_source_records_source_id'), 'raw_source_records', ['source_id'], unique=False)
    op.create_table('sites',
    sa.Column('id', sa.String(length=80), nullable=False),
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('synthetic', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('component_compatibility',
    sa.Column('id', sa.String(length=80), nullable=False),
    sa.Column('definition_id', sa.String(length=80), nullable=False),
    sa.Column('configuration_id', sa.String(length=80), nullable=False),
    sa.Column('effective_from', sa.DateTime(timezone=True), nullable=False),
    sa.Column('effective_to', sa.DateTime(timezone=True), nullable=True),
    sa.Column('verification', sa.String(length=80), nullable=False),
    sa.ForeignKeyConstraint(['configuration_id'], ['equipment_configurations.id'], ),
    sa.ForeignKeyConstraint(['definition_id'], ['component_definitions.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_component_compatibility_configuration_id'), 'component_compatibility', ['configuration_id'], unique=False)
    op.create_index(op.f('ix_component_compatibility_definition_id'), 'component_compatibility', ['definition_id'], unique=False)
    op.create_table('component_instances',
    sa.Column('id', sa.String(length=80), nullable=False),
    sa.Column('definition_id', sa.String(length=80), nullable=False),
    sa.Column('serial_number', sa.String(length=120), nullable=False),
    sa.Column('lot', sa.String(length=80), nullable=True),
    sa.Column('supplier', sa.String(length=120), nullable=False),
    sa.Column('revision', sa.String(length=40), nullable=False),
    sa.Column('disposition', sa.String(length=80), nullable=False),
    sa.Column('repair_cycle', sa.Integer(), nullable=False),
    sa.Column('refurbishment_status', sa.String(length=80), nullable=False),
    sa.Column('traceability_status', sa.String(length=80), nullable=False),
    sa.Column('manufactured_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['definition_id'], ['component_definitions.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('serial_number')
    )
    op.create_index(op.f('ix_component_instances_definition_id'), 'component_instances', ['definition_id'], unique=False)
    op.create_table('ingestion_originals',
    sa.Column('id', sa.String(length=80), nullable=False),
    sa.Column('run_id', sa.String(length=80), nullable=False),
    sa.Column('source', sa.String(length=120), nullable=False),
    sa.Column('ingested_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('original_json', sa.Text(), nullable=False),
    sa.Column('fingerprint', sa.String(length=64), nullable=False),
    sa.Column('row', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['run_id'], ['ingestion_runs.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_ingestion_originals_run_id'), 'ingestion_originals', ['run_id'], unique=False)
    op.create_table('pm_plans',
    sa.Column('id', sa.String(length=80), nullable=False),
    sa.Column('definition_id', sa.String(length=80), nullable=False),
    sa.Column('dimension', sa.String(length=80), nullable=False),
    sa.Column('threshold', sa.Float(), nullable=True),
    sa.Column('calendar_days', sa.Float(), nullable=True),
    sa.Column('unit', sa.String(length=40), nullable=False),
    sa.Column('basis', sa.String(length=120), nullable=False),
    sa.Column('source_document', sa.Text(), nullable=False),
    sa.Column('effective_from', sa.DateTime(timezone=True), nullable=False),
    sa.Column('effective_to', sa.DateTime(timezone=True), nullable=True),
    sa.Column('verification', sa.String(length=80), nullable=False),
    sa.ForeignKeyConstraint(['definition_id'], ['component_definitions.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_pm_plans_definition_id'), 'pm_plans', ['definition_id'], unique=False)
    op.create_table('specifications',
    sa.Column('id', sa.String(length=80), nullable=False),
    sa.Column('definition_id', sa.String(length=80), nullable=False),
    sa.Column('parameter', sa.String(length=120), nullable=False),
    sa.Column('unit', sa.String(length=40), nullable=True),
    sa.Column('nominal', sa.Float(), nullable=True),
    sa.Column('minimum', sa.Float(), nullable=True),
    sa.Column('maximum', sa.Float(), nullable=True),
    sa.Column('part_revision', sa.String(length=40), nullable=False),
    sa.Column('configuration_id', sa.String(length=80), nullable=False),
    sa.Column('source_document', sa.Text(), nullable=False),
    sa.Column('document_revision', sa.String(length=40), nullable=False),
    sa.Column('effective_from', sa.DateTime(timezone=True), nullable=False),
    sa.Column('verification', sa.String(length=80), nullable=False),
    sa.ForeignKeyConstraint(['configuration_id'], ['equipment_configurations.id'], ),
    sa.ForeignKeyConstraint(['definition_id'], ['component_definitions.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_specifications_configuration_id'), 'specifications', ['configuration_id'], unique=False)
    op.create_index(op.f('ix_specifications_definition_id'), 'specifications', ['definition_id'], unique=False)
    op.create_table('tools',
    sa.Column('id', sa.String(length=80), nullable=False),
    sa.Column('site_id', sa.String(length=80), nullable=False),
    sa.Column('configuration_id', sa.String(length=80), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('status', sa.String(length=40), nullable=False),
    sa.Column('phase', sa.String(length=80), nullable=False),
    sa.ForeignKeyConstraint(['configuration_id'], ['equipment_configurations.id'], ),
    sa.ForeignKeyConstraint(['site_id'], ['sites.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_index(op.f('ix_tools_configuration_id'), 'tools', ['configuration_id'], unique=False)
    op.create_index(op.f('ix_tools_site_id'), 'tools', ['site_id'], unique=False)
    op.create_table('chambers',
    sa.Column('id', sa.String(length=80), nullable=False),
    sa.Column('tool_id', sa.String(length=80), nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('status', sa.String(length=40), nullable=False),
    sa.ForeignKeyConstraint(['tool_id'], ['tools.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tool_id', 'name')
    )
    op.create_index(op.f('ix_chambers_tool_id'), 'chambers', ['tool_id'], unique=False)
    op.create_table('refurbishments',
    sa.Column('id', sa.String(length=80), nullable=False),
    sa.Column('component_id', sa.String(length=80), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('qualified', sa.Boolean(), nullable=False),
    sa.Column('findings', sa.Text(), nullable=False),
    sa.Column('source_record_id', sa.String(length=80), nullable=False),
    sa.ForeignKeyConstraint(['component_id'], ['component_instances.id'], ),
    sa.ForeignKeyConstraint(['source_record_id'], ['raw_source_records.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_refurbishments_component_id'), 'refurbishments', ['component_id'], unique=False)
    op.create_index(op.f('ix_refurbishments_source_record_id'), 'refurbishments', ['source_record_id'], unique=False)
    op.create_table('source_conflicts',
    sa.Column('id', sa.String(length=80), nullable=False),
    sa.Column('component_id', sa.String(length=80), nullable=True),
    sa.Column('field', sa.String(length=120), nullable=False),
    sa.Column('record_a_id', sa.String(length=80), nullable=False),
    sa.Column('record_b_id', sa.String(length=80), nullable=False),
    sa.Column('value_a', sa.Text(), nullable=False),
    sa.Column('value_b', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=80), nullable=False),
    sa.Column('decision', sa.Text(), nullable=True),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['component_id'], ['component_instances.id'], ),
    sa.ForeignKeyConstraint(['record_a_id'], ['raw_source_records.id'], ),
    sa.ForeignKeyConstraint(['record_b_id'], ['raw_source_records.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_source_conflicts_component_id'), 'source_conflicts', ['component_id'], unique=False)
    op.create_index(op.f('ix_source_conflicts_record_a_id'), 'source_conflicts', ['record_a_id'], unique=False)
    op.create_index(op.f('ix_source_conflicts_record_b_id'), 'source_conflicts', ['record_b_id'], unique=False)
    op.create_table('counter_samples',
    sa.Column('id', sa.String(length=80), nullable=False),
    sa.Column('chamber_id', sa.String(length=80), nullable=False),
    sa.Column('source', sa.String(length=120), nullable=False),
    sa.Column('dimension', sa.String(length=80), nullable=False),
    sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
    sa.Column('value', sa.Float(), nullable=False),
    sa.Column('modulus', sa.Float(), nullable=True),
    sa.Column('source_record_id', sa.String(length=80), nullable=False),
    sa.ForeignKeyConstraint(['chamber_id'], ['chambers.id'], ),
    sa.ForeignKeyConstraint(['source_record_id'], ['raw_source_records.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_counter_samples_chamber_id'), 'counter_samples', ['chamber_id'], unique=False)
    op.create_index(op.f('ix_counter_samples_source_record_id'), 'counter_samples', ['source_record_id'], unique=False)
    op.create_table('exposure_intervals',
    sa.Column('id', sa.String(length=80), nullable=False),
    sa.Column('chamber_id', sa.String(length=80), nullable=False),
    sa.Column('source', sa.String(length=120), nullable=False),
    sa.Column('dimension', sa.String(length=80), nullable=False),
    sa.Column('start', sa.DateTime(timezone=True), nullable=False),
    sa.Column('end', sa.DateTime(timezone=True), nullable=False),
    sa.Column('quality', sa.String(length=80), nullable=False),
    sa.Column('source_record_id', sa.String(length=80), nullable=False),
    sa.Column('value', sa.Float(), nullable=True),
    sa.CheckConstraint('"end" > "start"', name='ck_exposure_interval'),
    sa.ForeignKeyConstraint(['chamber_id'], ['chambers.id'], ),
    sa.ForeignKeyConstraint(['source_record_id'], ['raw_source_records.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_exposure_intervals_chamber_id'), 'exposure_intervals', ['chamber_id'], unique=False)
    op.create_index(op.f('ix_exposure_intervals_source_record_id'), 'exposure_intervals', ['source_record_id'], unique=False)
    op.create_table('failure_episodes',
    sa.Column('id', sa.String(length=80), nullable=False),
    sa.Column('chamber_id', sa.String(length=80), nullable=False),
    sa.Column('component_id', sa.String(length=80), nullable=True),
    sa.Column('failure_mode_id', sa.String(length=80), nullable=True),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('status', sa.String(length=80), nullable=False),
    sa.Column('attribution_status', sa.String(length=80), nullable=False),
    sa.Column('root_cause', sa.Text(), nullable=False),
    sa.Column('hypotheses', sa.JSON(), nullable=False),
    sa.Column('review_status', sa.String(length=80), nullable=False),
    sa.Column('deduplication_key', sa.String(length=160), nullable=False),
    sa.ForeignKeyConstraint(['chamber_id'], ['chambers.id'], ),
    sa.ForeignKeyConstraint(['component_id'], ['component_instances.id'], ),
    sa.ForeignKeyConstraint(['failure_mode_id'], ['failure_modes.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('deduplication_key')
    )
    op.create_index(op.f('ix_failure_episodes_chamber_id'), 'failure_episodes', ['chamber_id'], unique=False)
    op.create_index(op.f('ix_failure_episodes_component_id'), 'failure_episodes', ['component_id'], unique=False)
    op.create_index(op.f('ix_failure_episodes_failure_mode_id'), 'failure_episodes', ['failure_mode_id'], unique=False)
    op.create_table('fdc_points',
    sa.Column('id', sa.String(length=80), nullable=False),
    sa.Column('chamber_id', sa.String(length=80), nullable=False),
    sa.Column('component_id', sa.String(length=80), nullable=False),
    sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
    sa.Column('signal', sa.String(length=120), nullable=False),
    sa.Column('value', sa.Float(), nullable=False),
    sa.Column('unit', sa.String(length=40), nullable=False),
    sa.Column('state', sa.String(length=80), nullable=False),
    sa.Column('cohort', sa.String(length=80), nullable=False),
    sa.Column('source_record_id', sa.String(length=80), nullable=False),
    sa.ForeignKeyConstraint(['chamber_id'], ['chambers.id'], ),
    sa.ForeignKeyConstraint(['component_id'], ['component_instances.id'], ),
    sa.ForeignKeyConstraint(['source_record_id'], ['raw_source_records.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_fdc_points_chamber_id'), 'fdc_points', ['chamber_id'], unique=False)
    op.create_index(op.f('ix_fdc_points_component_id'), 'fdc_points', ['component_id'], unique=False)
    op.create_index(op.f('ix_fdc_points_source_record_id'), 'fdc_points', ['source_record_id'], unique=False)
    op.create_table('observation_coverage',
    sa.Column('id', sa.String(length=80), nullable=False),
    sa.Column('chamber_id', sa.String(length=80), nullable=False),
    sa.Column('source', sa.String(length=120), nullable=False),
    sa.Column('start', sa.DateTime(timezone=True), nullable=False),
    sa.Column('end', sa.DateTime(timezone=True), nullable=False),
    sa.Column('source_record_id', sa.String(length=80), nullable=False),
    sa.ForeignKeyConstraint(['chamber_id'], ['chambers.id'], ),
    sa.ForeignKeyConstraint(['source_record_id'], ['raw_source_records.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_observation_coverage_chamber_id'), 'observation_coverage', ['chamber_id'], unique=False)
    op.create_index(op.f('ix_observation_coverage_source_record_id'), 'observation_coverage', ['source_record_id'], unique=False)
    op.create_table('subsystems',
    sa.Column('id', sa.String(length=80), nullable=False),
    sa.Column('chamber_id', sa.String(length=80), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.ForeignKeyConstraint(['chamber_id'], ['chambers.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_subsystems_chamber_id'), 'subsystems', ['chamber_id'], unique=False)
    op.create_table('work_orders',
    sa.Column('id', sa.String(length=80), nullable=False),
    sa.Column('chamber_id', sa.String(length=80), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('kind', sa.String(length=80), nullable=False),
    sa.Column('status', sa.String(length=80), nullable=False),
    sa.Column('opened_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('source_record_id', sa.String(length=80), nullable=False),
    sa.ForeignKeyConstraint(['chamber_id'], ['chambers.id'], ),
    sa.ForeignKeyConstraint(['source_record_id'], ['raw_source_records.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_work_orders_chamber_id'), 'work_orders', ['chamber_id'], unique=False)
    op.create_index(op.f('ix_work_orders_source_record_id'), 'work_orders', ['source_record_id'], unique=False)
    op.create_table('assemblies',
    sa.Column('id', sa.String(length=80), nullable=False),
    sa.Column('subsystem_id', sa.String(length=80), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.ForeignKeyConstraint(['subsystem_id'], ['subsystems.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_assemblies_subsystem_id'), 'assemblies', ['subsystem_id'], unique=False)
    op.create_table('commissioning_milestones',
    sa.Column('id', sa.String(length=80), nullable=False),
    sa.Column('tool_id', sa.String(length=80), nullable=False),
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('planned_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('actual_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('failure_id', sa.String(length=80), nullable=True),
    sa.Column('critical_path_established', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['failure_id'], ['failure_episodes.id'], ),
    sa.ForeignKeyConstraint(['tool_id'], ['tools.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_commissioning_milestones_failure_id'), 'commissioning_milestones', ['failure_id'], unique=False)
    op.create_index(op.f('ix_commissioning_milestones_tool_id'), 'commissioning_milestones', ['tool_id'], unique=False)
    op.create_table('corrective_actions',
    sa.Column('id', sa.String(length=80), nullable=False),
    sa.Column('failure_id', sa.String(length=80), nullable=False),
    sa.Column('proposal', sa.Text(), nullable=False),
    sa.Column('validation_status', sa.String(length=80), nullable=False),
    sa.Column('owner', sa.String(length=120), nullable=False),
    sa.ForeignKeyConstraint(['failure_id'], ['failure_episodes.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_corrective_actions_failure_id'), 'corrective_actions', ['failure_id'], unique=False)
    op.create_table('downtime_intervals',
    sa.Column('id', sa.String(length=80), nullable=False),
    sa.Column('failure_id', sa.String(length=80), nullable=True),
    sa.Column('chamber_id', sa.String(length=80), nullable=False),
    sa.Column('start', sa.DateTime(timezone=True), nullable=False),
    sa.Column('end', sa.DateTime(timezone=True), nullable=False),
    sa.Column('category', sa.String(length=80), nullable=False),
    sa.Column('classification', sa.String(length=120), nullable=False),
    sa.Column('critical_path_hours', sa.Float(), nullable=True),
    sa.Column('source_record_id', sa.String(length=80), nullable=False),
    sa.CheckConstraint('"end" > "start"', name='ck_downtime_time'),
    sa.ForeignKeyConstraint(['chamber_id'], ['chambers.id'], ),
    sa.ForeignKeyConstraint(['failure_id'], ['failure_episodes.id'], ),
    sa.ForeignKeyConstraint(['source_record_id'], ['raw_source_records.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_downtime_intervals_chamber_id'), 'downtime_intervals', ['chamber_id'], unique=False)
    op.create_index(op.f('ix_downtime_intervals_failure_id'), 'downtime_intervals', ['failure_id'], unique=False)
    op.create_index(op.f('ix_downtime_intervals_source_record_id'), 'downtime_intervals', ['source_record_id'], unique=False)
    op.create_table('equipment_events',
    sa.Column('id', sa.String(length=80), nullable=False),
    sa.Column('chamber_id', sa.String(length=80), nullable=False),
    sa.Column('failure_id', sa.String(length=80), nullable=True),
    sa.Column('asserted_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('cleared_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('label', sa.String(length=200), nullable=False),
    sa.Column('synthetic_code', sa.String(length=80), nullable=False),
    sa.Column('symptom_role', sa.String(length=80), nullable=False),
    sa.Column('source_record_id', sa.String(length=80), nullable=False),
    sa.ForeignKeyConstraint(['chamber_id'], ['chambers.id'], ),
    sa.ForeignKeyConstraint(['failure_id'], ['failure_episodes.id'], ),
    sa.ForeignKeyConstraint(['source_record_id'], ['raw_source_records.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_equipment_events_chamber_id'), 'equipment_events', ['chamber_id'], unique=False)
    op.create_index(op.f('ix_equipment_events_failure_id'), 'equipment_events', ['failure_id'], unique=False)
    op.create_index(op.f('ix_equipment_events_source_record_id'), 'equipment_events', ['source_record_id'], unique=False)
    op.create_table('evidence',
    sa.Column('id', sa.String(length=80), nullable=False),
    sa.Column('failure_id', sa.String(length=80), nullable=False),
    sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
    sa.Column('kind', sa.String(length=80), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('quality', sa.String(length=80), nullable=False),
    sa.Column('source_record_id', sa.String(length=80), nullable=False),
    sa.ForeignKeyConstraint(['failure_id'], ['failure_episodes.id'], ),
    sa.ForeignKeyConstraint(['source_record_id'], ['raw_source_records.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_evidence_failure_id'), 'evidence', ['failure_id'], unique=False)
    op.create_index(op.f('ix_evidence_source_record_id'), 'evidence', ['source_record_id'], unique=False)
    op.create_table('maintenance_actions',
    sa.Column('id', sa.String(length=80), nullable=False),
    sa.Column('work_order_id', sa.String(length=80), nullable=False),
    sa.Column('component_id', sa.String(length=80), nullable=False),
    sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
    sa.Column('action', sa.String(length=120), nullable=False),
    sa.Column('findings', sa.Text(), nullable=False),
    sa.Column('confirmed_failure', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['component_id'], ['component_instances.id'], ),
    sa.ForeignKeyConstraint(['work_order_id'], ['work_orders.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_maintenance_actions_component_id'), 'maintenance_actions', ['component_id'], unique=False)
    op.create_index(op.f('ix_maintenance_actions_work_order_id'), 'maintenance_actions', ['work_order_id'], unique=False)
    op.create_table('pm_due_events',
    sa.Column('id', sa.String(length=80), nullable=False),
    sa.Column('plan_id', sa.String(length=80), nullable=False),
    sa.Column('component_id', sa.String(length=80), nullable=False),
    sa.Column('due_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('status', sa.String(length=40), nullable=False),
    sa.Column('completed_work_order_id', sa.String(length=80), nullable=True),
    sa.ForeignKeyConstraint(['completed_work_order_id'], ['work_orders.id'], ),
    sa.ForeignKeyConstraint(['component_id'], ['component_instances.id'], ),
    sa.ForeignKeyConstraint(['plan_id'], ['pm_plans.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_pm_due_events_completed_work_order_id'), 'pm_due_events', ['completed_work_order_id'], unique=False)
    op.create_index(op.f('ix_pm_due_events_component_id'), 'pm_due_events', ['component_id'], unique=False)
    op.create_index(op.f('ix_pm_due_events_plan_id'), 'pm_due_events', ['plan_id'], unique=False)
    op.create_table('replacement_events',
    sa.Column('id', sa.String(length=80), nullable=False),
    sa.Column('old_component_id', sa.String(length=80), nullable=False),
    sa.Column('new_component_id', sa.String(length=80), nullable=False),
    sa.Column('work_order_id', sa.String(length=80), nullable=False),
    sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.ForeignKeyConstraint(['new_component_id'], ['component_instances.id'], ),
    sa.ForeignKeyConstraint(['old_component_id'], ['component_instances.id'], ),
    sa.ForeignKeyConstraint(['work_order_id'], ['work_orders.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_replacement_events_new_component_id'), 'replacement_events', ['new_component_id'], unique=False)
    op.create_index(op.f('ix_replacement_events_old_component_id'), 'replacement_events', ['old_component_id'], unique=False)
    op.create_index(op.f('ix_replacement_events_work_order_id'), 'replacement_events', ['work_order_id'], unique=False)
    op.create_table('downtime_attributions',
    sa.Column('id', sa.String(length=80), nullable=False),
    sa.Column('downtime_id', sa.String(length=80), nullable=False),
    sa.Column('component_id', sa.String(length=80), nullable=False),
    sa.Column('weight', sa.Float(), nullable=False),
    sa.Column('status', sa.String(length=80), nullable=False),
    sa.Column('rationale', sa.Text(), nullable=False),
    sa.CheckConstraint('weight >= 0 AND weight <= 1', name='ck_attribution_weight'),
    sa.ForeignKeyConstraint(['component_id'], ['component_instances.id'], ),
    sa.ForeignKeyConstraint(['downtime_id'], ['downtime_intervals.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('downtime_id', 'component_id')
    )
    op.create_index(op.f('ix_downtime_attributions_component_id'), 'downtime_attributions', ['component_id'], unique=False)
    op.create_index(op.f('ix_downtime_attributions_downtime_id'), 'downtime_attributions', ['downtime_id'], unique=False)
    op.create_table('positions',
    sa.Column('id', sa.String(length=80), nullable=False),
    sa.Column('assembly_id', sa.String(length=80), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('exposure_source', sa.String(length=120), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.ForeignKeyConstraint(['assembly_id'], ['assemblies.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_positions_assembly_id'), 'positions', ['assembly_id'], unique=False)
    op.create_table('installations',
    sa.Column('id', sa.String(length=80), nullable=False),
    sa.Column('component_id', sa.String(length=80), nullable=False),
    sa.Column('position_id', sa.String(length=80), nullable=False),
    sa.Column('installed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('removed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.Column('removal_reason', sa.Text(), nullable=True),
    sa.Column('maintenance_reference', sa.String(length=100), nullable=True),
    sa.Column('source_record_id', sa.String(length=80), nullable=False),
    sa.CheckConstraint('removed_at IS NULL OR removed_at > installed_at', name='ck_install_time'),
    sa.ForeignKeyConstraint(['component_id'], ['component_instances.id'], ),
    sa.ForeignKeyConstraint(['position_id'], ['positions.id'], ),
    sa.ForeignKeyConstraint(['source_record_id'], ['raw_source_records.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_installations_component_id'), 'installations', ['component_id'], unique=False)
    op.create_index(op.f('ix_installations_position_id'), 'installations', ['position_id'], unique=False)
    op.create_index(op.f('ix_installations_source_record_id'), 'installations', ['source_record_id'], unique=False)
    op.create_index('uq_component_active', 'installations', ['component_id'], unique=True, sqlite_where=sa.text('removed_at IS NULL'), postgresql_where=sa.text('removed_at IS NULL'))
    op.create_index('uq_position_active', 'installations', ['position_id'], unique=True, sqlite_where=sa.text('removed_at IS NULL'), postgresql_where=sa.text('removed_at IS NULL'))


def downgrade():
    op.drop_index('uq_position_active', table_name='installations', sqlite_where=sa.text('removed_at IS NULL'), postgresql_where=sa.text('removed_at IS NULL'))
    op.drop_index('uq_component_active', table_name='installations', sqlite_where=sa.text('removed_at IS NULL'), postgresql_where=sa.text('removed_at IS NULL'))
    op.drop_index(op.f('ix_installations_source_record_id'), table_name='installations')
    op.drop_index(op.f('ix_installations_position_id'), table_name='installations')
    op.drop_index(op.f('ix_installations_component_id'), table_name='installations')
    op.drop_table('installations')
    op.drop_index(op.f('ix_positions_assembly_id'), table_name='positions')
    op.drop_table('positions')
    op.drop_index(op.f('ix_downtime_attributions_downtime_id'), table_name='downtime_attributions')
    op.drop_index(op.f('ix_downtime_attributions_component_id'), table_name='downtime_attributions')
    op.drop_table('downtime_attributions')
    op.drop_index(op.f('ix_replacement_events_work_order_id'), table_name='replacement_events')
    op.drop_index(op.f('ix_replacement_events_old_component_id'), table_name='replacement_events')
    op.drop_index(op.f('ix_replacement_events_new_component_id'), table_name='replacement_events')
    op.drop_table('replacement_events')
    op.drop_index(op.f('ix_pm_due_events_plan_id'), table_name='pm_due_events')
    op.drop_index(op.f('ix_pm_due_events_component_id'), table_name='pm_due_events')
    op.drop_index(op.f('ix_pm_due_events_completed_work_order_id'), table_name='pm_due_events')
    op.drop_table('pm_due_events')
    op.drop_index(op.f('ix_maintenance_actions_work_order_id'), table_name='maintenance_actions')
    op.drop_index(op.f('ix_maintenance_actions_component_id'), table_name='maintenance_actions')
    op.drop_table('maintenance_actions')
    op.drop_index(op.f('ix_evidence_source_record_id'), table_name='evidence')
    op.drop_index(op.f('ix_evidence_failure_id'), table_name='evidence')
    op.drop_table('evidence')
    op.drop_index(op.f('ix_equipment_events_source_record_id'), table_name='equipment_events')
    op.drop_index(op.f('ix_equipment_events_failure_id'), table_name='equipment_events')
    op.drop_index(op.f('ix_equipment_events_chamber_id'), table_name='equipment_events')
    op.drop_table('equipment_events')
    op.drop_index(op.f('ix_downtime_intervals_source_record_id'), table_name='downtime_intervals')
    op.drop_index(op.f('ix_downtime_intervals_failure_id'), table_name='downtime_intervals')
    op.drop_index(op.f('ix_downtime_intervals_chamber_id'), table_name='downtime_intervals')
    op.drop_table('downtime_intervals')
    op.drop_index(op.f('ix_corrective_actions_failure_id'), table_name='corrective_actions')
    op.drop_table('corrective_actions')
    op.drop_index(op.f('ix_commissioning_milestones_tool_id'), table_name='commissioning_milestones')
    op.drop_index(op.f('ix_commissioning_milestones_failure_id'), table_name='commissioning_milestones')
    op.drop_table('commissioning_milestones')
    op.drop_index(op.f('ix_assemblies_subsystem_id'), table_name='assemblies')
    op.drop_table('assemblies')
    op.drop_index(op.f('ix_work_orders_source_record_id'), table_name='work_orders')
    op.drop_index(op.f('ix_work_orders_chamber_id'), table_name='work_orders')
    op.drop_table('work_orders')
    op.drop_index(op.f('ix_subsystems_chamber_id'), table_name='subsystems')
    op.drop_table('subsystems')
    op.drop_index(op.f('ix_observation_coverage_source_record_id'), table_name='observation_coverage')
    op.drop_index(op.f('ix_observation_coverage_chamber_id'), table_name='observation_coverage')
    op.drop_table('observation_coverage')
    op.drop_index(op.f('ix_fdc_points_source_record_id'), table_name='fdc_points')
    op.drop_index(op.f('ix_fdc_points_component_id'), table_name='fdc_points')
    op.drop_index(op.f('ix_fdc_points_chamber_id'), table_name='fdc_points')
    op.drop_table('fdc_points')
    op.drop_index(op.f('ix_failure_episodes_failure_mode_id'), table_name='failure_episodes')
    op.drop_index(op.f('ix_failure_episodes_component_id'), table_name='failure_episodes')
    op.drop_index(op.f('ix_failure_episodes_chamber_id'), table_name='failure_episodes')
    op.drop_table('failure_episodes')
    op.drop_index(op.f('ix_exposure_intervals_source_record_id'), table_name='exposure_intervals')
    op.drop_index(op.f('ix_exposure_intervals_chamber_id'), table_name='exposure_intervals')
    op.drop_table('exposure_intervals')
    op.drop_index(op.f('ix_counter_samples_source_record_id'), table_name='counter_samples')
    op.drop_index(op.f('ix_counter_samples_chamber_id'), table_name='counter_samples')
    op.drop_table('counter_samples')
    op.drop_index(op.f('ix_source_conflicts_record_b_id'), table_name='source_conflicts')
    op.drop_index(op.f('ix_source_conflicts_record_a_id'), table_name='source_conflicts')
    op.drop_index(op.f('ix_source_conflicts_component_id'), table_name='source_conflicts')
    op.drop_table('source_conflicts')
    op.drop_index(op.f('ix_refurbishments_source_record_id'), table_name='refurbishments')
    op.drop_index(op.f('ix_refurbishments_component_id'), table_name='refurbishments')
    op.drop_table('refurbishments')
    op.drop_index(op.f('ix_chambers_tool_id'), table_name='chambers')
    op.drop_table('chambers')
    op.drop_index(op.f('ix_tools_site_id'), table_name='tools')
    op.drop_index(op.f('ix_tools_configuration_id'), table_name='tools')
    op.drop_table('tools')
    op.drop_index(op.f('ix_specifications_definition_id'), table_name='specifications')
    op.drop_index(op.f('ix_specifications_configuration_id'), table_name='specifications')
    op.drop_table('specifications')
    op.drop_index(op.f('ix_pm_plans_definition_id'), table_name='pm_plans')
    op.drop_table('pm_plans')
    op.drop_index(op.f('ix_ingestion_originals_run_id'), table_name='ingestion_originals')
    op.drop_table('ingestion_originals')
    op.drop_index(op.f('ix_component_instances_definition_id'), table_name='component_instances')
    op.drop_table('component_instances')
    op.drop_index(op.f('ix_component_compatibility_definition_id'), table_name='component_compatibility')
    op.drop_index(op.f('ix_component_compatibility_configuration_id'), table_name='component_compatibility')
    op.drop_table('component_compatibility')
    op.drop_table('sites')
    op.drop_index(op.f('ix_raw_source_records_source_id'), table_name='raw_source_records')
    op.drop_index(op.f('ix_raw_source_records_source'), table_name='raw_source_records')
    op.drop_table('raw_source_records')
    op.drop_table('ingestion_runs')
    op.drop_table('failure_modes')
    op.drop_table('equipment_configurations')
    op.drop_index(op.f('ix_component_definitions_supersedes_id'), table_name='component_definitions')
    op.drop_table('component_definitions')
    op.drop_table('audit_logs')
