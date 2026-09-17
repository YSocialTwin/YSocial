var MB_HASHTAG = (function() {
    function init() {
        var config = window.YS_DATA_MB_HASHTAG || {};
        if (window.InfiniteScroll && config.page !== undefined) {
            InfiniteScroll.init({
                apiEndpoint: '/'+config.expId+'/api/hashtag_posts/'+config.hashtagId,
                postsContainerId: 'posts-container',
                initialPage: config.page
            });
        }
    }

    document.addEventListener('DOMContentLoaded', init);

    return { init: init };
})();
