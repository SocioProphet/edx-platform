var define = window.define || RequireJS.define;

define(
  "js/ccx/view/feedback_message_view",
  [
    'backbone',
    'text!templates/ccx/underscore/feedback_alert.underscore'
  ],
  function (Backbone, feedbackAlertTemplate) {
    return Backbone.View.extend({

      initialize: function(options) {
        this.message = options.message;
        this.show =  true;
      },

      render: function() {
        this.$el.html(_.template(feedbackAlertTemplate) ({
          message: this.message,
          show: this.show
        }));
        this.showFeedbackMessage();
        return this;
      },

      showFeedbackMessage: function() {
        this.$('#notification-mini').removeClass('is-hiding');
        this.$('#notification-mini').addClass('is-shown');
        this.show =  true;
      },

      hideFeedbackMessage: function() {
        var self = this;
        this.$('#notification-mini').removeClass('is-shown');
        this.$('#notification-mini').addClass('is-hiding');
        this.show =  false;
        setTimeout(function(){
          self.render();
        },1000);
      }
    });
  }
);
