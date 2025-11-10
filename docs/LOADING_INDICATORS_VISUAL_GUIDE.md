# Visual Loading Indicator Examples

## Loading Overlay Appearance

The loading indicator appears as a full-screen overlay with:

```
┌─────────────────────────────────────────────────┐
│                                                 │
│          ┌─────────────────────────┐            │
│          │                         │            │
│          │      ⟳  (spinner)       │            │
│          │                         │            │
│          │  Starting experiment    │            │
│          │       server...         │            │
│          │                         │            │
│          └─────────────────────────┘            │
│                                                 │
└─────────────────────────────────────────────────┘
   Dark semi-transparent blurred background
```

**Visual Elements:**
- White rounded card in the center
- Blue animated spinner (rotating circle)
- Status message below spinner
- Dark overlay with blur effect
- Blocks all user interaction
- z-index: 99999 (always on top)

## Toast Notification Appearance

Toast notifications slide in from the top-right:

### Success Toast
```
┌────────────────────────────┐
│ ✓ Operation successful!    │
└────────────────────────────┘
  Green background (#d4edda)
  Green border (#c3e6cb)
  Dark green text (#155724)
```

### Error Toast
```
┌────────────────────────────┐
│ ✕ An error occurred!       │
└────────────────────────────┘
  Red background (#f8d7da)
  Red border (#f5c6cb)
  Dark red text (#721c24)
```

### Warning Toast
```
┌────────────────────────────┐
│ ⚠ Warning message!         │
└────────────────────────────┘
  Yellow background (#fff3cd)
  Yellow border (#ffeeba)
  Dark yellow text (#856404)
```

### Info Toast
```
┌────────────────────────────┐
│ ℹ Information message!     │
└────────────────────────────┘
  Blue background (#d1ecf1)
  Blue border (#bee5eb)
  Dark blue text (#0c5460)
```

**Toast Features:**
- Slides in from right with smooth animation
- Auto-dismisses after 3 seconds
- Can be manually dismissed
- Multiple toasts stack vertically
- Responsive to screen size

## Example Integration

### Before (No Feedback)
```html
<a href="/admin/start_experiment/1">
    <i class="mdi mdi-play-box-outline"></i>
</a>
```
User clicks → Nothing visible → Page reloads eventually

### After (With Loading Indicator)
```html
<a href="/admin/start_experiment/1" 
   onclick="showLoading('Starting experiment server...');">
    <i class="mdi mdi-play-box-outline"></i>
</a>
```
User clicks → Immediate overlay → Clear message → Auto-dismisses

## Animation Details

### Spinner Animation
- Rotates 360 degrees continuously
- 1 second per rotation
- Smooth linear animation
- Blue color (#5596e6)

### Toast Animation
- **Slide In:** 300ms ease-out from right
- **Stay:** 3000ms (default)
- **Slide Out:** 300ms ease-out to right

### Overlay Transition
- Fade in: 200ms
- Fade out: 200ms
- Backdrop blur: 2px

## Responsive Behavior

### Desktop (>800px)
- Loading card: 400px max width
- Toast: 250-400px width
- Toast position: 20px from top-right

### Mobile (<800px)
- Loading card: 90% screen width
- Toast: 90% screen width
- Toast position: 10px from top-right
- Smaller fonts for readability

## Accessibility

### Keyboard Navigation
- Loading overlay is not dismissible (intentional)
- Blocks all interaction during operation
- Auto-dismisses when operation completes

### Screen Readers
- Status messages are readable
- Spinner has semantic meaning
- Toast notifications are announced

### Color Contrast
- All text meets WCAG AA standards
- Icons reinforce color meaning
- High contrast between text and background

## Browser Compatibility

### Fully Supported
- Chrome 90+ ✅
- Firefox 88+ ✅
- Safari 14+ ✅
- Edge 90+ ✅

### Partial Support
- Older browsers: Overlay works, blur may not apply
- No JavaScript: Forms/links work normally

### Graceful Degradation
- Without CSS: Basic functionality remains
- Without JavaScript: Operations still work
- Slow connections: Loading shown immediately
