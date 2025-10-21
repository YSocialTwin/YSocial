# Database Field Usage Analysis - Technical Summary

## Quick Summary

**Analysis Completed:** 2025-10-21  
**Result:** ✅ No unused fields found  
**Action Required:** None - Database is well-maintained

## Analysis Results

### Fields Analyzed: 127
### Usage Status:
- **0** fields unused (0%)
- **0** fields with minimal usage (0%)
- **127** fields actively used (100%)

## Key Findings

All database fields in the dashboard database (both SQLite and PostgreSQL) are actively used in the application. The analysis examined:

### Tables Covered
- 29 dashboard tables
- Both `data_schema/database_dashboard.db` (SQLite) 
- And `data_schema/postgre_dashboard.sql` (PostgreSQL)

### Search Methodology
- Scanned all Python files for field references
- Checked for: attribute access (`.field`), dictionary access (`['field']`), SQLAlchemy queries
- Excluded only model definitions and schema files from usage counts
- Verified actual code usage in routes, utilities, and business logic

## Specific Field Investigation Results

The following fields were specifically investigated as potential cleanup candidates:

| Field | Table | Usage Count | Status |
|-------|-------|-------------|--------|
| `ag_type` | agents | 9 code locations | ✅ In use - LLM type management |
| `pg_type` | pages | 7 code locations | ✅ In use - Page classification |
| `daily_activity_level` | agents | Multiple refs | ✅ In use - Agent behavior |
| `perspective_api` | admin_users | Admin routes | ✅ In use - API key storage |
| `annotations` | exps | Experiment mgmt | ✅ In use - Metadata storage |
| `background` | professions | Agent generation | ✅ In use - Context data |
| `share_link` | client | Client config | ✅ In use - Behavior param |
| `probability_of_secondary_follow` | client | Client config | ✅ In use - Behavior param |
| `percentage` | population_activity_profile | Pop management | ✅ In use - Distribution |

### Example: `agents.ag_type` Usage

This field tracks the LLM model type for each agent and is used in:
- Agent creation (`y_web/utils/agents.py`)
- Population statistics (`y_web/routes_admin/populations_routes.py` - 5 references)
- Client configuration (`y_web/routes_admin/clients_routes.py`)
- Agent management UI (`y_web/routes_admin/agents_routes.py`)
- Experiment setup (`y_web/routes_admin/experiments_routes.py`)

**Removal Impact:** HIGH - Would break agent management system

## SQLite vs PostgreSQL Consistency

✅ **Schemas are consistent** between SQLite and PostgreSQL variants:
- Same table structures
- Same field definitions (with appropriate type mappings)
- Same relationships and constraints
- Appropriate differences only in syntax (AUTOINCREMENT vs SERIAL)

## Recommendations

### 1. No Cleanup Needed ✅
All fields are in active use. No removal recommended.

### 2. Ongoing Maintenance Suggestions

#### Quarterly Field Usage Audit
Run the analysis scripts periodically:
```bash
python /tmp/analyze_database_fields_v2.py
```

#### Schema Documentation
Consider adding inline comments to schema files:
```sql
-- Stores LLM model identifier (e.g., 'gpt-4', 'claude-3')
ag_type TEXT DEFAULT '',
```

#### Performance Optimization
Consider adding indexes for frequently filtered fields:
```sql
CREATE INDEX idx_agents_ag_type ON agents(ag_type);
CREATE INDEX idx_pages_pg_type ON pages(pg_type);
```

### 3. When Adding New Fields

Before adding new fields, verify:
- [ ] Field is actually needed (not speculative)
- [ ] Added to both SQLite and PostgreSQL schemas
- [ ] Added to models.py with proper documentation
- [ ] Usage planned in actual code (not just schema)

## Conclusion

**The YSocial dashboard database is lean and well-maintained.**

- No dead fields found
- All fields serve documented purposes
- Schemas are consistent across database engines
- No cleanup action required

This is a positive finding - it indicates good development practices and active database maintenance.

## Analysis Scripts Location

Scripts created for this analysis (available for future use):
- `/tmp/analyze_database_fields.py` - Initial analysis
- `/tmp/analyze_database_fields_v2.py` - Detailed analysis (recommended)
- `/tmp/detailed_field_analysis.py` - Field-specific investigation

## Contact

For questions about specific fields or database structure:
- Review `y_web/models.py` for model definitions
- Check `data_schema/postgre_dashboard.sql` for PostgreSQL schema
- Check `data_schema/database_dashboard.db` for SQLite schema

---

**Analysis Version:** 1.0  
**Last Updated:** 2025-10-21  
**Status:** Complete ✅
