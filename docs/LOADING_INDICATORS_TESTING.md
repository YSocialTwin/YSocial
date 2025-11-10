# Loading Indicators Testing Guide

## Overview
This document describes the loading indicators implementation and how to test them.

## What Was Implemented

### 1. Core Loading Indicator JavaScript (`loading-indicator.js`)
- Global loading overlay with spinner
- Custom message support
- Toast notification system (success, error, warning, info)
- Utility functions for forms and links
- Automatic dismissal on page navigation

### 2. Integration Points
The loading indicators have been integrated into the following operations:

#### Experiment Management (`experiment_details.html`)
- ✅ Start experiment server: "Starting experiment server..."
- ✅ Stop experiment server: "Stopping experiment server..."
- ✅ Load experiment interface: "Loading experiment interface..."
- ✅ Join experiment: "Joining experiment..."

#### JupyterLab (`experiment_details.html`)
- ✅ Start JupyterLab: "Starting JupyterLab..."
- ✅ Stop JupyterLab: "Stopping JupyterLab..."

#### Client Management (`experiment_details.html`)
- ✅ Start client: "Starting client..."
- ✅ Pause client: "Pausing client..."
- ✅ Delete client: "Deleting client..."

#### Agent Management (`agents.html`)
- ✅ Create agent: "Creating agent..."
- ✅ Delete orphaned agents: "Deleting orphaned agents..."

#### Population Management (`populations.html`)
- ✅ Create population: "Creating population..."
- ✅ Create empty population: "Creating empty population..."

#### Page Management (`pages.html`)
- ✅ Create page: "Creating page..."

#### Client Configuration (`clients.html`)
- ✅ Create client: "Creating client..."

#### Experiment Setup (`settings.html`)
- ✅ Create experiment: "Creating experiment..."
- ✅ Upload experiment: "Uploading experiment..."
- ✅ Copy experiment: "Copying experiment..."

## How to Test

### Manual Testing Steps

1. **Start the YSocial application:**
   ```bash
   python y_social.py
   ```

2. **Navigate to the admin dashboard:**
   - Go to `/admin/dashboard`
   - Login with admin credentials

3. **Test Experiment Operations:**
   - Go to Experiments > Click on an experiment
   - Click "Start Experiment" - You should see a loading overlay with "Starting experiment server..."
   - The overlay should disappear when the page reloads
   - Try the same for Stop, Load, and Join operations

4. **Test JupyterLab:**
   - If JupyterLab is enabled, click the JupyterLab start button
   - You should see "Starting JupyterLab..." overlay
   - The overlay shows with proper feedback

5. **Test Client Operations:**
   - In the experiment details page, start a client
   - You should see "Starting client..." overlay
   - Test pause and delete operations similarly

6. **Test Creation Forms:**
   - Navigate to Agents page and create a new agent
   - Fill in the form and click Create
   - You should see "Creating agent..." overlay
   - Repeat for Populations, Pages, and Clients

7. **Test Experiment Creation:**
   - Go to Experiments page
   - Try creating a new experiment
   - You should see "Creating experiment..." overlay
   - Test upload and copy operations similarly

### Visual Verification

The loading indicator should:
- ✅ Appear immediately when an operation starts
- ✅ Show a centered overlay with a spinning loader
- ✅ Display the appropriate message for each operation
- ✅ Have a blurred background (backdrop-filter)
- ✅ Disappear when the page reloads or operation completes
- ✅ Prevent user interaction during loading

### Toast Notifications

Toast notifications can be triggered with:
```javascript
showToast('Success message', 'success');
showToast('Error message', 'error');
showToast('Warning message', 'warning');
showToast('Info message', 'info');
```

They should:
- ✅ Appear in the top-right corner
- ✅ Slide in with animation
- ✅ Auto-dismiss after 3 seconds
- ✅ Show appropriate colors and icons

## Technical Details

### JavaScript Functions Available

1. **showLoading(message)**
   - Displays the loading overlay
   - Optional message parameter (default: "Loading...")

2. **hideLoading()**
   - Hides the loading overlay
   - Safe to call multiple times

3. **showToast(message, type, duration)**
   - Shows a toast notification
   - Types: 'success', 'error', 'warning', 'info'
   - Duration in milliseconds (default: 3000)

4. **addLoadingToElement(element, message)**
   - Adds loading behavior to a link/button

5. **addLoadingToForm(form, message)**
   - Adds loading behavior to a form submission

6. **withLoading(message, ajaxFunction)**
   - Wraps an AJAX call with loading indicator

### Browser Compatibility

The implementation uses:
- Vanilla JavaScript (no dependencies)
- CSS3 animations
- Flexbox layout
- backdrop-filter (modern browsers)

Tested on:
- Chrome/Edge (modern versions)
- Firefox (modern versions)
- Safari (modern versions)

## Troubleshooting

### Loading indicator doesn't appear
- Check browser console for JavaScript errors
- Verify `loading-indicator.js` is loaded in the network tab
- Ensure `head.html` includes the script tag

### Loading indicator doesn't disappear
- Check if page actually reloads after operation
- For AJAX operations, ensure `hideLoading()` is called in success/error handlers
- Check browser console for errors

### Toast notifications don't show
- Verify `showToast()` function exists in window scope
- Check browser console for errors
- Ensure proper parameters are passed

## Future Enhancements

Potential improvements:
- Add progress percentage for long-running operations
- Add cancel button for cancelable operations
- Integrate with WebSocket for real-time status updates
- Add loading indicator to more operations as needed
- Customize animation styles
- Add sound notifications (optional)
