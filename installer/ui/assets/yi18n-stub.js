// login-scene.js asks window.YI18n for two short strings; the launcher is English-only.
window.YI18n = { t: function (key) { return key; }, ready: Promise.resolve() };
