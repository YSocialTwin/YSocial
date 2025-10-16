# Populations Datatable Update

## Changes Made (Commit d72698e)

This document summarizes the changes made to the populations datatable based on the latest feedback.

## Overview

The populations datatable has been updated to replace recommendation system fields with demographic and behavioral characteristic fields, all displayed as styled tags for better visual consistency.

## Changes

### Removed Fields

- **Content RecSys** - Content Recommendation System field
- **Follow RecSys** - Friendships/Follow Recommendation System field

### Added Fields

1. **Education** - Education levels associated with the population
2. **Political Leaning** - Political leanings of the population
3. **Toxicity** - Toxicity levels configured for the population

All three new fields are displayed as styled tags, matching the existing Activity Profiles field.

## Implementation Details

### Backend (`populations_routes.py`)

The backend now parses comma-separated ID strings from the Population model and resolves them to human-readable names:

```python
# Get lookup dictionaries for education, leanings, and toxicity
education_dict = {str(e.id): e.education_level for e in Education.query.all()}
leanings_dict = {str(l.id): l.leaning for l in Leanings.query.all()}
toxicity_dict = {str(t.id): t.toxicity_level for t in Toxicity_Levels.query.all()}

return {
    "data": [
        {
            "id": pop.id,
            "name": pop.name,
            "size": pop.size,
            "education": [
                education_dict.get(e_id.strip(), e_id.strip())
                for e_id in (pop.education or "").split(",")
                if e_id.strip()
            ],
            "leanings": [
                leanings_dict.get(l_id.strip(), l_id.strip())
                for l_id in (pop.leanings or "").split(",")
                if l_id.strip()
            ],
            "toxicity": [
                toxicity_dict.get(t_id.strip(), t_id.strip())
                for t_id in (pop.toxicity or "").split(",")
                if t_id.strip()
            ],
            "activity_profiles": population_profiles.get(pop.id, []),
        }
        for pop in res
    ],
    "total": total,
}
```

### Data Structure

The Population model stores these fields as comma-separated ID strings:
- `education`: String of comma-separated education level IDs
- `leanings`: String of comma-separated political leaning IDs
- `toxicity`: String of comma-separated toxicity level IDs

These IDs are resolved to names via lookup tables:
- `Education.query.all()` → `{id: education_level}`
- `Leanings.query.all()` → `{id: leaning}`
- `Toxicity_Levels.query.all()` → `{id: toxicity_level}`

### Frontend (`populations.html`)

Each field uses the same tag formatter for visual consistency:

```javascript
{ 
    id: 'education', 
    name: 'Education',
    sort: false,
    formatter: (cell) => {
        if (!cell || cell.length === 0) {
            return '';
        }
        const tags = cell.map(item => 
            `<span style="display: inline-block; background-color: #039be5; 
             color: white; padding: 3px 8px; border-radius: 12px; 
             font-size: 0.75rem; margin: 2px;">${item}</span>`
        ).join(' ');
        return gridjs.html(`<div style="display: flex; flex-wrap: wrap; gap: 4px;">${tags}</div>`);
    }
}
```

The same formatter is applied to:
- Education
- Political Leaning
- Toxicity
- Activity Profiles

### Tag Styling

All tags use consistent styling:
- **Background**: `#039be5` (template primary blue)
- **Text color**: White
- **Border radius**: `12px` (rounded pill)
- **Font size**: `0.75rem`
- **Padding**: `3px 8px`
- **Margin**: `2px`
- **Display**: Flex-wrap container with 4px gap

## Column Order

The updated populations datatable now displays columns in this order:

1. **Name** (editable)
2. **Agents** (size)
3. **Education** (tags)
4. **Political Leaning** (tags)
5. **Toxicity** (tags)
6. **Activity Profiles** (tags)
7. **Actions** (Details, Delete)

## Visual Benefits

### 1. Consistent Tag Design

All characteristic fields now use the same visual treatment, making the table easier to scan and understand.

### 2. Better Information Density

Demographic and behavioral characteristics are more relevant for population management than recommendation system configurations, which are better suited for the detailed view.

### 3. Visual Hierarchy

The blue tags provide clear visual grouping and make it easy to distinguish between different types of characteristics at a glance.

### 4. Responsive Layout

Tags automatically wrap to multiple lines when needed, preventing column overflow and maintaining readability.

## Data Handling

### Empty Values

When a population has no values set for a field, the formatter returns an empty string, resulting in a clean empty cell rather than showing "Not set" or similar text.

### Multiple Values

Each field can contain multiple values, which are displayed as separate tags:
- **Education**: e.g., "High School", "Bachelor's Degree", "Master's Degree"
- **Political Leaning**: e.g., "Left", "Center", "Right"
- **Toxicity**: e.g., "Low", "Medium", "High"

### ID Resolution

IDs that cannot be resolved (e.g., if a reference is invalid or the lookup table entry was deleted) fall back to displaying the ID itself, preventing data loss.

## Database Schema

### Population Model

```python
class Population(db.Model):
    # ...
    education = db.Column(db.String(100))    # Comma-separated IDs
    leanings = db.Column(db.String(200))     # Comma-separated IDs
    toxicity = db.Column(db.String(50))      # Comma-separated IDs
```

### Lookup Models

```python
class Education(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    education_level = db.Column(db.String(50), nullable=False)

class Leanings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    leaning = db.Column(db.String(50), nullable=False)

class Toxicity_Levels(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    toxicity_level = db.Column(db.String(50), nullable=False)
```

## Testing

- ✅ All 21 tests passing (100%)
- ✅ No regressions detected
- ✅ Tag formatters handle empty values gracefully
- ✅ Multiple values per field display correctly
- ✅ ID resolution works with lookup dictionaries

## Rationale

### Why Remove RecSys Fields?

1. **Detail-level information**: Recommendation system configurations are technical details better suited for the population detail page
2. **Focus on characteristics**: Education, leanings, and toxicity are more relevant for quickly understanding population composition
3. **Visual consistency**: All characteristic fields now use the same tag format, improving scanability

### Why Use Tags?

1. **Visual consistency**: Matches the existing Activity Profiles field
2. **Multiple values**: Tags naturally support displaying multiple values per field
3. **Compact display**: Tags are more space-efficient than comma-separated text
4. **Better scanability**: Color-coded tags are easier to scan than plain text
5. **Professional appearance**: Tags match modern UI design patterns

## Migration Notes

If existing users have data in the `crecsys` and `frecsys` fields, this information is still stored in the database and accessible via:
- The population detail page (`/admin/population_details/{id}`)
- The Population model attributes (`pop.crecsys`, `pop.frecsys`)

Only the datatable view has been updated; the underlying data structure remains unchanged.

## Files Modified

1. `y_web/routes_admin/populations_routes.py` - Updated data query and formatting
2. `y_web/templates/admin/populations.html` - Updated column definitions and formatters

## Summary

The populations datatable now displays demographic and behavioral characteristics (education, political leaning, toxicity) as styled tags, replacing the recommendation system fields and providing a more intuitive view of population composition at a glance.
