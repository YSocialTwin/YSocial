var MB_FEED = (function() {
    function init() {
        var config = window.YS_DATA_MB_FEED || {};
        if (window.InfiniteScroll && config.page !== undefined) {
            InfiniteScroll.init({
                apiEndpoint: '/'+config.expId+'/api/feed/'+config.userId+'/'+config.timeline+'/'+config.mode,
                postsContainerId: 'posts-container',
                initialPage: config.page
            });
        }
    }

    document.addEventListener('DOMContentLoaded', init);

    return { init: init };
})();
