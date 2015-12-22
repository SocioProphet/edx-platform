var define = window.define || RequireJS.define;  // jshint ignore:line

define("js/ccx/model/rename_ccx_name_model",
  ['backbone'], function (Backbone) {
  'use strict';
  return Backbone.Model.extend({
    defaults: {
      name: ''
    }
  });
});
