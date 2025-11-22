# Blog Post Announcement Feature

## Overview

The YSocial admin dashboard now includes an automatic blog post announcement system that notifies administrators when new blog posts are published on https://y-not.social/blog/.

The system fetches the RSS feed from **https://y-not.social/feed.xml** with a 10-second timeout to ensure it doesn't delay application startup. If the feed is unreachable, the application continues to start normally and logs a warning message.

## Features

### Automatic Blog Post Detection
- **Startup Check**: The system checks for new blog posts every time the application starts
- **RSS Feed URL**: https://y-not.social/feed.xml
- **Timeout**: 10-second timeout to prevent startup delays
- **RSS/Atom Support**: Compatible with both RSS 2.0 and Atom feed formats
- **Non-Intrusive**: If the blog feed is unavailable, the application continues to run normally with a warning logged

### Admin Dashboard Banner
- **Visual Notification**: New blog posts appear as an orange-themed banner in the admin dashboard
- **Post Information**: Displays the blog post title and publication date
- **Action Buttons**: 
  - "Read Article" - Opens the blog post in a new tab and marks it as read
  - Dismiss (X) - Marks the post as read without opening it

### Persistent State
- **Database Storage**: Blog posts are stored in the `blog_posts` table
- **Read Status**: Once marked as read, a post won't appear again
- **Multiple Posts**: The system tracks multiple blog posts independently

## Technical Details

### Database Schema

**SQLite:**
```sql
CREATE TABLE blog_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    published_at TEXT,
    link TEXT,
    is_read INTEGER DEFAULT 0,
    latest_check_on TEXT
);
```

**PostgreSQL:**
```sql
CREATE TABLE blog_posts (
    id SERIAL PRIMARY KEY,
    title TEXT,
    published_at TEXT,
    link TEXT,
    is_read BOOLEAN DEFAULT FALSE,
    latest_check_on TEXT
);
```

### API Endpoints

**Mark Blog Post as Read:**
```
POST /admin/mark_blog_post_read/<post_id>
```
- **Access**: Admin users only
- **Returns**: JSON response with success/error status

### RSS Feed Support

The system fetches blog posts from:
- **Primary URL**: `https://y-not.social/feed.xml`
- **Timeout**: 10 seconds (prevents startup delays)
- **SSL Verification**: Enabled for security

It supports both:
- **RSS 2.0**: Standard RSS format with `<item>` elements
- **Atom**: Modern feed format with `<entry>` elements

## Migration

For existing installations, the system automatically:
1. Detects if the `blog_posts` table exists
2. Creates it if missing (SQLite only - PostgreSQL uses schema file)
3. Runs on every application startup (idempotent)

## User Interface

### Banner Appearance
- **Color**: Orange gradient (distinct from blue release banners)
- **Icon**: Post icon
- **Position**: Below release banner (if present)
- **Z-index**: 999 (below release banner at 1000)

### Interaction
```javascript
// Clicking "Read Article"
markBlogPostAsRead(postId) // Marks as read via API
→ Opens link in new tab
→ Hides banner

// Clicking dismiss (X)
dismissBlogPost(postId) // Marks as read via API
→ Hides banner
```

## Development

### Testing
Run the blog post tests:
```bash
python3 y_web/tests/test_blog_posts.py
```

Tests cover:
- RSS 2.0 parsing
- Atom feed parsing
- Error handling
- Database migration

### Manual Testing
1. Start the application
2. Log in as an admin user
3. Check for blog post banner in dashboard
4. Test "Read Article" button
5. Test dismiss button
6. Verify banner doesn't reappear after marking as read

## Configuration

No configuration is required. The feature:
- Activates automatically on startup
- Only shows to admin users
- Gracefully handles errors (logs warnings if feed unavailable)

## Troubleshooting

### Banner Not Appearing
- Check that you're logged in as an admin user
- Verify the blog feed is accessible
- Check application logs for error messages during startup

### Database Migration Issues
For SQLite:
```bash
# Manually verify table exists
sqlite3 y_web/db/dashboard.db ".schema blog_posts"
```

For PostgreSQL:
```sql
-- Manually verify table exists
SELECT * FROM information_schema.tables 
WHERE table_name = 'blog_posts';
```

### API Errors
Check that:
- User has admin role
- Blog post ID exists in database
- Database connection is active

## Future Enhancements

Potential improvements for future versions:
- Per-user read status (instead of global)
- Configurable RSS feed URL
- Blog post summary preview
- Multiple blog post notifications
- Email notifications for new posts
- Admin settings to enable/disable feature
