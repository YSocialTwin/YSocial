var AdminFeeds = (function() {

    // ── Image Feeds ────────────────────────────────────────────────────────

    var _imageFeeds = [];
    var _currentSubreddit = '';

    function setParseStatus(state, message) {
        var statusEl = document.getElementById('parse_status');
        statusEl.replaceChildren();
        var wrapper = document.createElement('span');
        if (state === 'error') wrapper.style.color = '#e74c3c';
        else if (state === 'success') wrapper.style.color = '#27ae60';
        var icon = document.createElement('i');
        if (state === 'loading') icon.className = 'mdi mdi-loading mdi-spin';
        else if (state === 'success') icon.className = 'mdi mdi-check-circle';
        else icon.className = 'mdi mdi-alert-circle';
        wrapper.appendChild(icon);
        wrapper.appendChild(document.createTextNode(' ' + message));
        statusEl.appendChild(wrapper);
    }

    function parseSubreddit() {
        var subreddit = document.getElementById('subreddit_name').value.trim().toLowerCase();
        if (!subreddit) { alert('Please enter a subreddit name'); return; }
        _currentSubreddit = subreddit;
        setParseStatus('loading', 'Parsing...');
        document.getElementById('parse_result').style.display = 'block';
        document.getElementById('sample_images').replaceChildren();
        fetch('/admin/api/parse_image_feed', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({subreddit: subreddit})
        })
        .then(function(r) { return r.json().then(function(data) { return {ok: r.ok, data: data}; }); })
        .then(function(res) {
            if (!res.ok || res.data.error) { setParseStatus('error', res.data.error || 'Could not parse subreddit.'); return; }
            setParseStatus('success', 'Found ' + res.data.image_count + ' images (' + res.data.nsfw_filtered + ' NSFW filtered)');
            var sampleDiv = document.getElementById('sample_images');
            sampleDiv.replaceChildren();
            res.data.sample_images.forEach(function(url) {
                var img = document.createElement('img');
                img.src = url;
                img.style.cssText = 'width: 60px; height: 60px; object-fit: cover; border-radius: 4px;';
                img.onerror = function() { this.style.display = 'none'; };
                sampleDiv.appendChild(img);
            });
        })
        .catch(function(e) { setParseStatus('error', e.message || 'Unexpected error'); });
    }

    function addParsedSubreddit() {
        if (!_currentSubreddit) { alert('Please parse a subreddit first'); return; }
        var interestsSelect = document.getElementById('parsed_interests');
        var selectedInterests = Array.from(interestsSelect.selectedOptions).map(function(opt) { return opt.value; });
        if (selectedInterests.length === 0) { alert('Please select at least one interest'); return; }
        if (_imageFeeds.some(function(f) { return f.subreddit === _currentSubreddit; })) { alert('This subreddit is already added'); return; }
        _imageFeeds.push({ subreddit: _currentSubreddit, interests: selectedInterests });
        updateFeedsDisplay();
        document.getElementById('subreddit_name').value = '';
        document.getElementById('parse_result').style.display = 'none';
        _currentSubreddit = '';
    }

    function removeFeed(index) {
        _imageFeeds.splice(index, 1);
        updateFeedsDisplay();
    }

    function uploadImageFeeds() {
        var config = window.YS_DATA_FEEDS || {};
        var expId = config.expId;
        var fileInput = document.getElementById('image_upload_file');
        var mode = document.getElementById('image_upload_mode').value;
        if (!fileInput.files[0]) { alert('Please select a file'); return; }
        var formData = new FormData();
        formData.append('file', fileInput.files[0]);
        formData.append('mode', mode);
        fetch('/admin/upload_image_feeds/' + expId, { method: 'POST', body: formData })
        .then(function(r) { return r.json().then(function(data) { return {ok: r.ok, data: data}; }); })
        .then(function(res) {
            if (!res.ok || res.data.error) throw new Error(res.data.error || 'Upload failed');
            window.location.reload();
        })
        .catch(function(error) { alert(error.message || 'Upload failed'); });
    }

    function exportImageFeeds() {
        var blob = new Blob([JSON.stringify(_imageFeeds, null, 2)], {type: 'application/json'});
        var url = URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = url;
        a.download = 'image_feeds.json';
        a.click();
        URL.revokeObjectURL(url);
    }

    function updateFeedsDisplay() {
        var listDiv = document.getElementById('image_feeds_list');
        var countSpan = document.getElementById('feed_count');
        document.getElementById('image_feeds_json').value = JSON.stringify(_imageFeeds);
        countSpan.textContent = _imageFeeds.length;
        listDiv.replaceChildren();
        if (_imageFeeds.length === 0) {
            var emptyState = document.createElement('p');
            emptyState.style.color = '#999';
            emptyState.textContent = 'No image feeds configured.';
            listDiv.appendChild(emptyState);
            return;
        }
        var table = document.createElement('table');
        table.className = 'table is-fullwidth is-striped';
        table.style.fontSize = '0.9em';
        var thead = document.createElement('thead');
        var headerRow = document.createElement('tr');
        ['Subreddit', 'Interests', ''].forEach(function(label, index) {
            var th = document.createElement('th');
            if (index === 2) th.style.width = '50px';
            else th.textContent = label;
            headerRow.appendChild(th);
        });
        thead.appendChild(headerRow);
        table.appendChild(thead);
        var tbody = document.createElement('tbody');
        _imageFeeds.forEach(function(feed, index) {
            var row = document.createElement('tr');
            var subredditCell = document.createElement('td');
            subredditCell.textContent = 'r/' + feed.subreddit;
            row.appendChild(subredditCell);
            var interestsCell = document.createElement('td');
            (feed.interests || []).forEach(function(interest) {
                var tag = document.createElement('span');
                tag.className = 'tag is-info is-light';
                tag.style.margin = '2px';
                tag.textContent = interest;
                interestsCell.appendChild(tag);
            });
            row.appendChild(interestsCell);
            var actionCell = document.createElement('td');
            var actionLink = document.createElement('a');
            actionLink.href = 'javascript:void(0)';
            actionLink.style.color = '#e74c3c';
            actionLink.addEventListener('click', (function(i) { return function() { removeFeed(i); }; })(index));
            var icon = document.createElement('i');
            icon.className = 'mdi mdi-delete';
            actionLink.appendChild(icon);
            actionCell.appendChild(actionLink);
            row.appendChild(actionCell);
            tbody.appendChild(row);
        });
        table.appendChild(tbody);
        listDiv.appendChild(table);
    }

    function initImageFeeds() {
        var config = window.YS_DATA_FEEDS || {};
        _imageFeeds = config.imageFeeds || [];
        updateFeedsDisplay();
    }

    // ── RSS Feeds ──────────────────────────────────────────────────────────

    var _rssFeeds = [];
    var _parsedRssFeed = null;

    function parseRssFeed() {
        var feedUrl = document.getElementById('rss_feed_url').value.trim();
        if (!feedUrl) { alert('Please enter an RSS feed URL'); return; }
        fetch('/admin/api/parse_rss_feed', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({feed_url: feedUrl})
        })
        .then(function(r) { return r.json().then(function(data) { return {ok: r.ok, data: data}; }); })
        .then(function(res) {
            if (!res.ok || res.data.error) throw new Error(res.data.error || 'Could not parse RSS feed');
            _parsedRssFeed = res.data;
            document.getElementById('rss_parse_name').textContent = res.data.name || '-';
            document.getElementById('rss_parse_site').textContent = res.data.url_site || '-';
            document.getElementById('rss_parse_description').textContent = res.data.description || 'No description available';
            document.getElementById('rss_parse_entries').textContent = res.data.entries_count;
            document.getElementById('rss_parse_result').style.display = 'block';
        })
        .catch(function(error) { alert(error.message || 'Could not parse RSS feed'); });
    }

    function addParsedRssFeed() {
        if (!_parsedRssFeed) { alert('Please parse a feed first'); return; }
        if (_rssFeeds.some(function(feed) { return feed.feed_url === _parsedRssFeed.feed_url; })) {
            alert('This RSS feed is already configured'); return;
        }
        _rssFeeds.push(_parsedRssFeed);
        updateRssFeedsDisplay();
        document.getElementById('rss_feed_url').value = '';
        document.getElementById('rss_parse_result').style.display = 'none';
        _parsedRssFeed = null;
    }

    function removeRssFeed(index) {
        _rssFeeds.splice(index, 1);
        updateRssFeedsDisplay();
    }

    function updateRssFeedsDisplay() {
        var container = document.getElementById('rss_feeds_list');
        var count = document.getElementById('rss_feed_count');
        var hiddenInput = document.getElementById('rss_feeds_json');
        count.textContent = _rssFeeds.length;
        hiddenInput.value = JSON.stringify(_rssFeeds);
        container.replaceChildren();
        if (!_rssFeeds.length) {
            var emptyState = document.createElement('p');
            emptyState.style.color = '#999';
            emptyState.textContent = 'No RSS feeds configured.';
            container.appendChild(emptyState);
            return;
        }
        var table = document.createElement('table');
        table.className = 'table is-fullwidth is-striped';
        table.style.fontSize = '0.9em';
        var thead = document.createElement('thead');
        var headerRow = document.createElement('tr');
        ['Name', 'Site', 'Feed URL', ''].forEach(function(label, index) {
            var th = document.createElement('th');
            if (index === 3) th.style.width = '50px';
            else th.textContent = label;
            headerRow.appendChild(th);
        });
        thead.appendChild(headerRow);
        table.appendChild(thead);
        var tbody = document.createElement('tbody');
        _rssFeeds.forEach(function(feed, index) {
            var row = document.createElement('tr');
            var nameCell = document.createElement('td');
            nameCell.textContent = feed.name || '';
            row.appendChild(nameCell);
            var siteCell = document.createElement('td');
            siteCell.textContent = feed.url_site || '';
            row.appendChild(siteCell);
            var urlCell = document.createElement('td');
            urlCell.style.wordBreak = 'break-all';
            urlCell.textContent = feed.feed_url || '';
            row.appendChild(urlCell);
            var actionCell = document.createElement('td');
            var actionLink = document.createElement('a');
            actionLink.href = 'javascript:void(0)';
            actionLink.style.color = '#e74c3c';
            actionLink.addEventListener('click', (function(i) { return function() { removeRssFeed(i); }; })(index));
            var icon = document.createElement('i');
            icon.className = 'mdi mdi-delete';
            actionLink.appendChild(icon);
            actionCell.appendChild(actionLink);
            row.appendChild(actionCell);
            tbody.appendChild(row);
        });
        table.appendChild(tbody);
        container.appendChild(table);
    }

    function uploadRssFeeds() {
        var config = window.YS_DATA_RSS || {};
        var expId = config.expId;
        var fileInput = document.getElementById('rss_upload_file');
        var mode = document.getElementById('rss_upload_mode').value;
        if (!fileInput.files[0]) { alert('Please select a file'); return; }
        var formData = new FormData();
        formData.append('file', fileInput.files[0]);
        formData.append('mode', mode);
        fetch('/admin/upload_rss_feeds/' + expId, { method: 'POST', body: formData })
        .then(function(r) { return r.json().then(function(data) { return {ok: r.ok, data: data}; }); })
        .then(function(res) {
            if (!res.ok || res.data.error) throw new Error(res.data.error || 'Upload failed');
            window.location.reload();
        })
        .catch(function(error) { alert(error.message || 'Upload failed'); });
    }

    function initRssFeeds() {
        var config = window.YS_DATA_RSS || {};
        _rssFeeds = config.rssFeeds || [];
        updateRssFeedsDisplay();
    }

    return {
        parseSubreddit: parseSubreddit,
        addParsedSubreddit: addParsedSubreddit,
        removeFeed: removeFeed,
        uploadImageFeeds: uploadImageFeeds,
        exportImageFeeds: exportImageFeeds,
        parseRssFeed: parseRssFeed,
        addParsedRssFeed: addParsedRssFeed,
        removeRssFeed: removeRssFeed,
        uploadRssFeeds: uploadRssFeeds,
        initImageFeeds: initImageFeeds,
        initRssFeeds: initRssFeeds
    };
})();

document.addEventListener('DOMContentLoaded', function() {
    if (document.getElementById('image_feeds_list')) {
        AdminFeeds.initImageFeeds();
    }
    if (document.getElementById('rss_feeds_list')) {
        AdminFeeds.initRssFeeds();
    }
});
