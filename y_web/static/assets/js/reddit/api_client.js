(function (global, $) {
    'use strict';

    if (!$) {
        return;
    }

    function rejectWith(message) {
        return $.Deferred().reject(new Error(message)).promise();
    }

    function ajaxJson(options) {
        return $.ajax(options).then(
            function (response) {
                if (response && response.success === true) {
                    return response;
                }
                var message = (response && response.error) ? response.error : 'Unexpected server response.';
                return rejectWith(message);
            },
            function (xhr) {
                var message = 'Network request failed.';
                if (xhr && xhr.responseJSON && xhr.responseJSON.error) {
                    message = xhr.responseJSON.error;
                } else if (xhr && xhr.statusText) {
                    message = xhr.statusText;
                }
                return rejectWith(message);
            }
        );
    }

    function postJson(url, payload) {
        return ajaxJson({
            url: url,
            method: 'POST',
            contentType: 'application/json',
            data: JSON.stringify(payload || {}),
        });
    }

    function postForm(url, formData) {
        return ajaxJson({
            url: url,
            method: 'POST',
            data: formData,
            processData: false,
            contentType: false,
        });
    }

    function getJson(url, data) {
        return ajaxJson({
            url: url,
            method: 'GET',
            data: data || {},
        });
    }

    function getExpId() {
        return (window.redditFeedConfig && window.redditFeedConfig.expId) || '';
    }

    var Api = {
        vote: function (postId, action) {
            var expId = getExpId();
            return postJson('/api/reddit/' + expId + '/vote', {
                post_id: postId,
                action: action,
            }).then(function (response) {
                return response.data;
            });
        },

        createPost: function (contentOrPayload, url) {
            var expId = getExpId();
            var payload = {};
            if (contentOrPayload && typeof contentOrPayload === 'object') {
                payload = $.extend({}, contentOrPayload);
            } else {
                payload = { content: contentOrPayload };
            }
            if (url && !payload.url) {
                payload.url = url;
            }
            return postJson('/api/reddit/' + expId + '/post', payload).then(function (response) {
                return response.data;
            });
        },

        uploadMedia: function (file) {
            var expId = getExpId();
            var formData = new FormData();
            formData.append('file', file);
            return postForm('/api/reddit/' + expId + '/upload_media', formData).then(function (response) {
                return response.data;
            });
        },

        uploadImage: function (file) {
            var expId = getExpId();
            var formData = new FormData();
            formData.append('file', file);
            return postForm('/api/reddit/' + expId + '/upload_image', formData).then(function (response) {
                return response.data;
            });
        },

        createComment: function (parentId, content, clientActionId) {
            var expId = getExpId();
            var payload = {
                parent_id: parentId,
                content: content,
            };
            if (clientActionId) {
                payload.client_action_id = clientActionId;
            }
            return postJson('/api/reddit/' + expId + '/comment', payload).then(function (response) {
                return response.data;
            });
        },

        deletePost: function (postId) {
            var expId = getExpId();
            return postJson('/api/reddit/' + expId + '/post/' + postId + '/delete', {}).then(function (response) {
                return response.data;
            });
        },

        fetchFeed: function (params) {
            var expId = getExpId();
            return getJson('/api/reddit/' + expId + '/feed', params).then(function (response) {
                return response;
            });
        },

        fetchSearch: function (params) {
            var expId = getExpId();
            return getJson('/api/reddit/' + expId + '/search', params).then(function (response) {
                return response;
            });
        },

        fetchThread: function (postId) {
            var expId = getExpId();
            return getJson('/api/reddit/' + expId + '/thread/' + postId).then(function (response) {
                return response.data;
            });
        },

        enrichArticle: function (articleId, force) {
            var expId = getExpId();
            return postJson('/api/reddit/' + expId + '/enrich/article/' + articleId, {
                force: !!force,
            }).then(function (response) {
                return response.data;
            });
        },

        enrichImage: function (imageId, force) {
            var expId = getExpId();
            return postJson('/api/reddit/' + expId + '/enrich/image/' + imageId, {
                force: !!force,
            }).then(function (response) {
                return response.data;
            });
        },
    };

    global.RedditApi = Api;
})(window, window.jQuery);
