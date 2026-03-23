var MB_EMOTIONS = (function() {
    function init() {
        var config = window.YS_DATA_MB_EMOTIONS || {};
        if (window.InfiniteScroll && config.page !== undefined) {
            InfiniteScroll.init({
                apiEndpoint: '/'+config.expId+'/api/emotion/'+config.emotionId,
                postsContainerId: 'posts-container',
                initialPage: config.page
            });
        }
    }

    document.addEventListener('DOMContentLoaded', init);

    return { init: init };
})();
