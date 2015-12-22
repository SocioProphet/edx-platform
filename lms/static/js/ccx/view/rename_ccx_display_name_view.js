var define = window.define || RequireJS.define;

define(
  "js/ccx/view/rename_ccx_display_name_view",
  [
    'backbone',
    'underscore',
    'gettext',
    'js/ccx/view/feedback_message_view',
    'text!templates/ccx/underscore/display_name.underscore'
  ],
  function (Backbone, _, gettext, FeedbackMessageView, editTeamTemplate) {

    return Backbone.View.extend({
      events: {
        'click .ccx-display-name-heading': 'editDisplayNameHandler',
        'click .ccx-edit-display_name-btn': 'editDisplayNameHandler',
        'mouseover .ccx-display-name-heading': 'showEditButtonHandler',
        'mouseout .ccx-display-name-heading': 'hideEditButtonHandler',
        'focusout .edit-ccx-display-name': 'saveDisplayNameHandler'
      },

      initialize: function(options) {
        this.editDisplayName = false;
        this.$alertContainer = options.$alertContainer;
        this.renameDisplayNameUrl = options.renameDisplayNameUrl;
      },

      render: function() {
        this.$el.html(_.template(editTeamTemplate) ({
          editDisplayName: this.editDisplayName,
          displayName: this.collection.getDisplayName()
        }));
        this.hideEditButtonHandler();

        return this;
      },

      showEditButtonHandler: function() {
        this.$('.ccx-edit-display_name-btn').show();
      },

      hideEditButtonHandler: function() {
        this.$('.ccx-edit-display_name-btn').hide();
      },

      editDisplayNameHandler: function(e) {
        e.preventDefault();
        this.editDisplayName = true;
        this.render();
      },

      cancelEditModeHandler: function() {
        this.editDisplayName = false;
        this.render();
      },

      saveDisplayNameHandler: function() {
        var newDisplayName = $.trim($('.edit-ccx-display-name').val());
        var oldDisplayName = this.collection.getDisplayName();

        if (newDisplayName !== "" && newDisplayName !== oldDisplayName) {
          var self = this;
          this.ccxFeedbackMessageView = new FeedbackMessageView({
            el: this.$alertContainer,
            message: gettext('Saving CCX display name')
          });
          this.ccxFeedbackMessageView.render();
          $.post(this.renameDisplayNameUrl, { name: newDisplayName }, function(data) {
            if (data.status === 'ok') {
              self.editDisplayName = false;
              self.collection.setDisplayName(newDisplayName);
              self.ccxFeedbackMessageView.hideFeedbackMessage();
              self.render();
            }
          });
        } else {
          this.cancelEditModeHandler();
        }
      }
    });
  }
);
