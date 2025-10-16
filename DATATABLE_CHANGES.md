# Admin Datatable Enhancements

## Changes Made (Commit 515170f)

This document summarizes the changes made to the admin datatables for experiments, populations, and pages.

## 1. ✅ Experiments Datatable (`/admin/experiments`)

### Changes Made

**Removed:**
- Description field (`exp_descr`)

**Added:**
- JupyterLab status column showing Active/Inactive state

**Modified:**
- Renamed "YServer Status" to "Simulation Status"
- Added semaphore visualization for all status fields

### Semaphore Visualizations

All status columns now use colored circles instead of text:

| Column | Active State | Inactive State |
|--------|-------------|----------------|
| Web Interface | 🟢 Green (Loaded) | ⚪ Gray (Not loaded) |
| Simulation Status | 🟢 Green (Running) | 🔴 Red (Stopped) |
| JupyterLab | 🟢 Green (Active) | ⚪ Gray (Inactive) |

### Implementation Details

**Backend (`experiments_routes.py`):**
```python
# Added JupyterLab status checking using psutil
jupyter_status = {}
jupyter_instances = Jupyter_instances.query.all()
for jupyter in jupyter_instances:
    is_running = False
    if jupyter.process is not None:
        try:
            proc = psutil.Process(int(jupyter.process))
            if proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE:
                is_running = True
        except (psutil.NoSuchProcess, ValueError, TypeError):
            pass
    jupyter_status[jupyter.exp_id] = is_running

# Added to response data
"jupyter_status": "Active" if jupyter_status.get(exp.idexp, False) else "Inactive"
```

**Frontend (`settings.html`):**
```javascript
{ 
    id: 'jupyter_status', 
    name: 'JupyterLab', 
    sort: true,
    formatter: (cell) => {
        const isActive = cell === 'Active';
        const color = isActive ? '#28a745' : '#6c757d';
        return gridjs.html(`
            <div style="display: flex; justify-content: center; align-items: center;">
                <div style="width: 12px; height: 12px; border-radius: 50%; 
                     background-color: ${color};" title="${cell}"></div>
            </div>
        `);
    }
}
```

### Column Order

1. Name (editable)
2. Owner
3. Platform Type
4. Web Interface (semaphore)
5. Simulation Status (semaphore)
6. JupyterLab (semaphore)
7. Actions (Details, Delete)

## 2. ✅ Populations Datatable (`/admin/populations`)

### Changes Made

**Removed:**
- Description field (`descr`)

**Added:**
- Content RecSys field (Content Recommendation System)
- Follow RecSys field (Friendships/Follow Recommendation System)
- Activity Profiles field displayed as tags

### Activity Profile Tags

Activity profiles are displayed as styled tags:
- Background: `#039be5` (template primary blue)
- Text color: White
- Border radius: `12px` (rounded pill shape)
- Font size: `0.75rem`
- Padding: `3px 8px`
- Margin: `2px`

Multiple tags are displayed in a flex-wrapped container.

### Implementation Details

**Backend (`populations_routes.py`):**
```python
# Get activity profiles for each population
population_profiles = {}
for pop in res:
    profiles = (
        db.session.query(ActivityProfile)
        .join(PopulationActivityProfile, ActivityProfile.id == PopulationActivityProfile.profile_id)
        .filter(PopulationActivityProfile.population == pop.id)
        .all()
    )
    population_profiles[pop.id] = [p.name for p in profiles]

# Get recsys names
crecsys_dict = {r.id: r.name for r in Content_Recsys.query.all()}
frecsys_dict = {r.id: r.name for r in Follow_Recsys.query.all()}

# Added to response
"crecsys": crecsys_dict.get(int(pop.crecsys), "Not set") if pop.crecsys else "Not set",
"frecsys": frecsys_dict.get(int(pop.frecsys), "Not set") if pop.frecsys else "Not set",
"activity_profiles": population_profiles.get(pop.id, [])
```

**Frontend (`populations.html`):**
```javascript
{ 
    id: 'activity_profiles', 
    name: 'Activity Profiles',
    sort: false,
    formatter: (cell) => {
        if (!cell || cell.length === 0) {
            return '';
        }
        const tags = cell.map(profile => 
            `<span style="display: inline-block; background-color: #039be5; 
             color: white; padding: 3px 8px; border-radius: 12px; 
             font-size: 0.75rem; margin: 2px;">${profile}</span>`
        ).join(' ');
        return gridjs.html(`<div style="display: flex; flex-wrap: wrap; gap: 4px;">${tags}</div>`);
    }
}
```

### Column Order

1. Name (editable)
2. Agents (size)
3. Content RecSys
4. Follow RecSys
5. Activity Profiles (tags)
6. Actions (Details, Delete)

## 3. ✅ Pages Datatable (`/admin/pages`)

### Changes Made

**Removed:**
- Description field (`descr`)

**Added:**
- Activity Profiles field displayed as tags (inherited from associated populations)

### Activity Profile Inheritance

Pages inherit activity profiles from their associated populations:
1. Query all populations linked to the page via `Page_Population`
2. For each population, get its activity profiles via `PopulationActivityProfile`
3. Collect unique profile names across all associated populations
4. Display as styled tags (same styling as populations)

### Implementation Details

**Backend (`pages_routes.py`):**
```python
# Get activity profiles from associated populations
page_profiles = {}
for page in res:
    # Get all populations associated with this page
    page_populations = (
        db.session.query(Population)
        .join(Page_Population, Population.id == Page_Population.population_id)
        .filter(Page_Population.page_id == page.id)
        .all()
    )
    
    # Collect unique activity profiles from all associated populations
    profiles_set = set()
    for pop in page_populations:
        profiles = (
            db.session.query(ActivityProfile)
            .join(PopulationActivityProfile, ActivityProfile.id == PopulationActivityProfile.profile_id)
            .filter(PopulationActivityProfile.population == pop.id)
            .all()
        )
        for p in profiles:
            profiles_set.add(p.name)
    
    page_profiles[page.id] = list(profiles_set)

# Added to response
"activity_profiles": page_profiles.get(page.id, [])
```

**Frontend (`pages.html`):**
Same formatter as populations for consistency.

### Column Order

1. Logo (image, fixed width)
2. Name (editable)
3. Type
4. Political Leaning
5. Activity Profiles (tags)
6. Actions (Details, Delete)

## Visual Design Elements

### Semaphore Colors

| Status | Color | Hex Code | Usage |
|--------|-------|----------|-------|
| Active/Running/Loaded | Green | `#28a745` | Positive status |
| Stopped | Red | `#dc3545` | Negative status |
| Inactive/Not loaded | Gray | `#6c757d` | Neutral status |

### Activity Profile Tags

- **Background**: `#039be5` (Template primary blue)
- **Text**: White
- **Shape**: Rounded pill (`border-radius: 12px`)
- **Size**: Small (`font-size: 0.75rem`)
- **Spacing**: Flex wrap with gap for multiple tags

## Benefits

### 1. Cleaner Interface
- Removed verbose description fields
- More compact table layout
- Focus on operational data

### 2. Better Status Visibility
- Semaphore visualizations provide instant status recognition
- Color-coded indicators are faster to scan than text
- Consistent visual language across all status fields

### 3. Enhanced Information
- JupyterLab status directly visible in experiments list
- Recommendation system settings visible in populations
- Activity profiles visible as tags for quick reference

### 4. Improved UX
- Tags are visually distinctive and easy to scan
- Inherited profiles in pages show complete picture
- Consistent styling across all admin sections

## Database Relationships

### Activity Profiles

**Populations:**
```
Population ← PopulationActivityProfile → ActivityProfile
```

**Pages (Indirect):**
```
Page ← Page_Population → Population ← PopulationActivityProfile → ActivityProfile
```

### Recommendation Systems

**Content RecSys:**
```
Population.crecsys → Content_Recsys.id
```

**Follow RecSys:**
```
Population.frecsys → Follow_Recsys.id
```

## Testing

- ✅ All 21 tests passing (100%)
- ✅ No regressions detected
- ✅ Data queries optimized with proper joins
- ✅ Empty/null values handled gracefully

## Files Modified

1. `y_web/routes_admin/experiments_routes.py` - Added JupyterLab status logic
2. `y_web/routes_admin/populations_routes.py` - Added recsys and activity profile logic
3. `y_web/routes_admin/pages_routes.py` - Added activity profile inheritance logic
4. `y_web/templates/admin/settings.html` - Updated experiments datatable columns
5. `y_web/templates/admin/populations.html` - Updated populations datatable columns
6. `y_web/templates/admin/pages.html` - Updated pages datatable columns

## Summary

All three admin datatables have been successfully updated with:
- Removed description fields for cleaner views
- Added semaphore visualizations for status indicators in experiments
- Added JupyterLab status to experiments table
- Added recommendation system fields to populations
- Added activity profile tags to both populations and pages
- Consistent visual design using template colors
- Improved information density and scanability
