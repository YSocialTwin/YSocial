/**
 * YWeb frontend plugin loader (core).
 *
 * Reads window.YS_EDUCATYON_MODULES (an array injected by
 * templates/shared/plugin_loader.html, populated server-side by
 * y_web.src.external_runtime.plugin_loader.active_modules_context) and, for
 * each active module, injects its stylesheet and entry script.
 *
 * If the array is absent or empty — which is the case on every page where
 * no frontend plugin suite is installed, or none of its modules are enabled
 * for the current experiment — this file does nothing at all. That is the
 * "zero impact when disabled" guarantee at the JS layer.
 *
 * Each module is loaded defensively: a failure to load one module's script
 * or stylesheet is logged to the console and does not affect any other
 * module or the core page.
 */
(function () {
  'use strict';

  var MODULES = window.YS_EDUCATYON_MODULES;
  if (!Array.isArray(MODULES) || MODULES.length === 0) return;

  MODULES.forEach(function (mod) {
    try {
      if (!mod || !mod.module_id) return;

      if (mod.frontend_style) {
        var link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = mod.frontend_style;
        link.onerror = function () {
          console.warn('[plugin-core] failed to load stylesheet for module "' + mod.module_id + '"');
        };
        document.head.appendChild(link);
      }

      if (mod.frontend_entry) {
        var script = document.createElement('script');
        script.src = mod.frontend_entry;
        script.async = false; // preserve order + keep document.currentScript reliable
        script.dataset.educatyonModuleId = mod.module_id;
        script.dataset.educatyonExpId = String(mod.exp_id);
        script.dataset.educatyonApiBase = mod.api_base || '';
        script.dataset.educatyonConfig = JSON.stringify(mod.config || {});
        script.onerror = function () {
          console.warn('[plugin-core] failed to load script for module "' + mod.module_id + '" — module disabled on this page.');
        };
        document.body.appendChild(script);
      }
    } catch (e) {
      console.warn('[plugin-core] error initializing module "' + (mod && mod.module_id) + '":', e);
    }
  });
})();
