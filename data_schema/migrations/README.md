# Database Migrations

## Opinion Evolution Cache

### Migration 001: Add opinion_evolution_cache table

**Purpose**: Optimize opinion evolution animation performance by caching pre-computed statistics.

**File**: `001_add_opinion_evolution_cache.sql`

### How to Apply

#### PostgreSQL:
```bash
psql -U your_username -d your_database_name -f 001_add_opinion_evolution_cache.sql
```

#### SQLite (if using SQLite for dashboard):
The migration will be automatically applied via SQLAlchemy when the application starts.

### Cache Behavior

- Cache entries are stored for each combination of (experiment_id, day, hour, topic_id)
- Entries expire after 5 minutes to balance performance and freshness
- Cache is automatically populated on first request and reused for subsequent requests
- Old cache entries can be cleaned up periodically

### Performance Impact

- **Before**: Each animation frame requires querying all opinions up to that time point, which grows linearly with simulation duration
- **After**: First request computes and caches; subsequent requests use cache (5min expiry)
- **Expected improvement**: 10-100x faster for animations after initial cache warmup

### Cache Cleanup

To clean up old cache entries (optional):

```sql
-- Remove cache entries older than 1 day
DELETE FROM opinion_evolution_cache WHERE created_at < NOW() - INTERVAL '1 day';

-- Remove all cache for a specific experiment
DELETE FROM opinion_evolution_cache WHERE exp_id = <experiment_id>;
```

### Monitoring Cache Usage

```sql
-- Check cache size and distribution
SELECT exp_id, COUNT(*) as cache_entries, 
       MIN(created_at) as oldest_entry, 
       MAX(created_at) as newest_entry
FROM opinion_evolution_cache
GROUP BY exp_id
ORDER BY exp_id;

-- Check total cache size
SELECT COUNT(*) as total_entries, 
       pg_size_pretty(pg_total_relation_size('opinion_evolution_cache')) as table_size
FROM opinion_evolution_cache;
```
