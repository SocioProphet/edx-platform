var define = window.define || RequireJS.define;  // jshint ignore:line

define(
  "js/ccx/collection/rename_ccx_name_collection",
  [
    'backbone',
    "js/ccx/model/rename_ccx_name_model"
  ],
  function (Backbone, renameCCXNameModel) {
    'use strict';
    return Backbone.Collection.extend({
      model: renameCCXNameModel,

      getDisplayNameJson: function() {
        var jsonObject = this.toJSON();

        if (jsonObject && jsonObject.length > 0) {
          return jsonObject[0];
        }
        return jsonObject;
      },

      getDisplayName: function() {
        var jsonObject = this.getDisplayNameJson();
        if (jsonObject) {
          return jsonObject.name;
        }
      },

      setDisplayName: function(displayName) {
        this.reset({
          name: displayName
        })
      }
    });
  }
);
