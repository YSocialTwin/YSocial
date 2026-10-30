/**
 * Optional sections of the agent form (admin/agents), as in the population form: a switch shows the section and
 * enables its fields (a disabled fieldset is not submitted), the picture settings follow their own switch and the
 * image model is one of the proposed alternatives or any Hugging Face model id.
 */
(function () {
  'use strict';

  var SECTIONS = [
    { box: 'include_appearance', wrapper: 'appearance-config-wrapper', kind: 'appearance' },
    { box: 'include_photo_sharing', wrapper: 'photo-sharing-config-wrapper', kind: 'photo' },
    { box: 'include_dating', wrapper: 'dating-config-wrapper', kind: 'dating' }
  ];

  function on(id) {
    var el = document.getElementById(id);
    return !!(el && el.checked);
  }

  function sync() {
    SECTIONS.forEach(function (section) {
      var enabled = on(section.box);
      var wrapper = document.getElementById(section.wrapper);
      if (wrapper) { wrapper.classList.toggle('d-none', !enabled); }
      document.querySelectorAll('[data-optional-section="' + section.kind + '"]').forEach(function (el) {
        el.disabled = !enabled;
      });
    });
    var pictures = on('include_appearance') && on('generate_profile_pictures');
    var box = document.getElementById('profile-pictures-config');
    if (box) { box.classList.toggle('d-none', !pictures); }
    var fields = document.getElementById('profile-pictures-fields');
    if (fields) { fields.disabled = !pictures; }
  }

  document.addEventListener('DOMContentLoaded', function () {
    SECTIONS.map(function (s) { return s.box; }).concat(['generate_profile_pictures']).forEach(function (id) {
      var el = document.getElementById(id);
      if (el) { el.addEventListener('change', sync); }
    });
    document.querySelectorAll('[data-diffusion-select]').forEach(function (select) {
      var text = select.closest('.dating-diffusion').querySelector('[data-diffusion-text]');
      select.addEventListener('change', function () {
        if (select.value === '__other__') { text.hidden = false; text.value = ''; text.focus(); }
        else { text.value = select.value; text.hidden = true; }
      });
    });
    sync();
  });
})();
