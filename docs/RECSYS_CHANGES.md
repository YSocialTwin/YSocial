# Recommender System Configuration Changes

## Summary

This change moves the recommender system (recsys) configuration from the population and agent levels to the client level. This allows the same population to be reused across multiple experiments with different recsys settings.

## Changes Made

### Database Schema

**Client Model** (`y_web/models.py`)
- Added `crecsys` field (VARCHAR(50), nullable) - Content recommendation system
  - Examples: 'default', 'random', 'popularity-based', 'collaborative-filtering'
  - Values are defined in the `content_recsys` database table
- Added `frecsys` field (VARCHAR(50), nullable) - Follow recommendation system
  - Examples: 'default', 'random', 'similarity-based', 'social-graph'
  - Values are defined in the `follow_recsys` database table

Note: While these fields are nullable in the database schema, the UI requires selection when creating a client.

### Backend Routes

**clients_routes.py**
- `create_client()`: Now accepts `recsys_type` and `frecsys_type` from form
- `create_client()`: Stores recsys values in Client model
- `create_client()`: Sets recsys in population JSON file from client's recsys (not agent's)
- `update_recsys()`: Updates Client model's recsys fields in addition to User_mgmt
- `clients()`: Passes crecsys and frecsys options to template

**populations_routes.py**
- `create_population()`: No longer accepts or stores recsys values
- `populations()`: No longer passes crecsys/frecsys to template

**agents_routes.py**
- `create_agent()`: No longer accepts or stores recsys values
- `agent_data()`: No longer passes crecsys/frecsys to template

### Frontend Templates

**clients.html**
- Added "Recommendation Systems" section with Content RecSys and Friendship RecSys dropdowns

**populations.html**
- Removed "Recommendation Systems" section with recsys selection fields

**agents.html**
- Removed Content RecSys and Friendship RecSys fields from agent creation form

**population_details.html**
- Removed recsys update form
- Changed recsys display to show "Not set (configured per client)" when the value is NULL or empty string

**client_details.html**
- Updated to display client's recsys instead of population's recsys

### Database Migration

**migrations/add_recsys_to_client.sql**
- SQL script to add crecsys and frecsys columns to existing client tables

### Tests

**test_client_form_fields.py**
- Added `test_recsys_field_handling()` to verify recsys fields can be extracted from form

## Migration Instructions

### For New Installations
No action needed. SQLAlchemy will create tables with the new columns automatically.

### For Existing Databases

#### SQLite
```bash
sqlite3 path/to/your/database.db < migrations/add_recsys_to_client.sql
```

#### PostgreSQL
```bash
psql -d your_database_name -f migrations/add_recsys_to_client.sql
```

## Backward Compatibility

- Population and Agent models retain their recsys fields for backward compatibility with existing data
- Existing populations with recsys set will display them as read-only in population_details
- New populations and agents will not have recsys set
- New client configurations should specify recsys settings via the UI dropdowns (fields are nullable in database but UI provides default selection)

## Usage Flow

1. Create or select a population (no recsys configuration needed)
2. Create a client for an experiment
3. Select the population for the client
4. **Select Content RecSys and Friendship RecSys for the client** (required via UI, first option selected by default)
5. When the client is instantiated, all agents in the population JSON file will use the client's recsys settings

## Benefits

- ✅ Same population can be reused across multiple experiments with different recsys settings
- ✅ Recsys configuration is centralized at the experiment/client level
- ✅ Cleaner separation of concerns (population defines agents, client defines simulation parameters)
- ✅ Easier to compare different recsys approaches with the same population
