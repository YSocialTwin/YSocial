/**
 * Open an external URL in the system's default browser.
 * This function works in both regular browser mode and PyInstaller desktop mode.
 * 
 * @param {Event} event - The click event (to prevent default link behavior)
 * @param {string} url - The URL to open
 */
function openExternalUrl(event, url) {
    event.preventDefault();
    
    // Try using the backend endpoint first (works in PyInstaller mode)
    fetch('/admin/open_external_url', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        credentials: 'same-origin',
        body: JSON.stringify({ url: url })
    }).then(response => {
        if (!response.ok) {
            // Fallback to window.open if backend fails (e.g., in regular browser mode)
            console.log('Backend open_external_url failed, falling back to window.open');
            window.open(url, '_blank');
        }
    }).catch(error => {
        console.error('Error opening external URL:', error);
        // Fallback to window.open on network error
        window.open(url, '_blank');
    });
}
