require.config({
  baseUrl: '/static',
  paths: {
    jquery: 'js/vendor/jquery.min',
    flat: 'js/flat-ui.min',
    noty: 'js/vendor/jquery.noty.packaged.min',
    mustache: 'js/vendor/mustache',
    moment: 'js/vendor/moment',
    spinner: 'js/vendor/spin.min'
  },
  shim: {
    flat: {
      deps: ['jquery']
    },
    mustache: {
      deps: ['jquery']
    },
    noty: {
      deps: ['jquery']
    }
  }
});

require(['jquery', 'mustache', 'spinner', 'noty', 'flat', 'moment'], function ($, Mustache, Spinner) {
    var CasesCache = {};
    $.ajaxSetup({
      cache: false
    });

    var notyOpt = {
      layout: 'topCenter',
//      theme: 'bootstrapTheme',
      timeout: 2000,
      maxVisible: 2
    };

    var getCases = function () {
      $.ajax({'type': 'GET', 'url': '/case/', 'dataType': 'json'}).done(function (data) {
        if (spinner) {
          spinner.stop();
        }
        if (data.err || data.hasOwnProperty('err')) {
          noty($.extend({}, notyOpt, {text: 'Get cases fail!', type: 'error'}));
          return;
        }
        var $ul = $('#ul_cases');
        var _loop = [];
        for (var i in data) {
          CasesCache[data[i].number] = data[i];
          _loop.push({
            finished: data[i].finished,
            number: data[i].number,
            status: ($.trim(data[i].currentstatus) ? data[i].currentstatus : 'unknown'),
            lastcheck: (data[i].lastcheck ? moment.utc(data[i].lastcheck).local().format("MM/DD/YYYY h:mm a") : 'unknown time')
          });
        }
        $ul.html(Mustache.render($('#listTpl').html(), {loop: _loop}));
        $ul.on('click', '.btndelete', confirmDeleteFun);
        $ul.on('click', '.btndetail', detailFun);
      });
    };

    var confirmDeleteFun = function (e) {
      e.preventDefault();
      var $modal = $('#div_modal_sm');
      $modal.find('.modal-title').html('Delete this case?');
      $modal.find('.btn-danger').removeAttr('disabled').unbind('click').bind('click', {el: $(this)}, deleteFun);
      $modal.modal('show');
    };

    var deleteFun = function (e) {
      e.preventDefault();
      $(this).attr('disabled', 'true');
      var $this = e.data.el;
      var $li = $this.parents('li');
      var $modal = $('#div_modal_sm');
      $.ajax({
        'type': 'delete',
        'url': '/case/' + $this.attr('caseid') + '/',
        'dataType': 'json'
      }).done(function (data) {
        if (data.ok && data.hasOwnProperty('ok')) {
          noty($.extend({}, notyOpt, {text: 'Delete case success!', type: 'success'}));
          $li.remove();
          if ($('#ul_cases').find('li').length < 1) {
            $('#ul_cases').append('<li><div class="todo-content"><div class="row"><div class="col-md-8"><p>No record found.</p></div></div></div></li>');
          }
          $modal.find('.btn-danger').unbind('click');
          $modal.modal('hide');
        } else {
          noty($.extend({}, notyOpt, {text: 'Delete case fail! ' + data.err, type: 'error'}));
        }
      });
    };

    var detailFun = function (e) {
      e.preventDefault();
      var data = CasesCache[$(this).attr('caseid')];
      data.lastcheck = (data.lastcheck ? moment.utc(data.lastcheck).local().format() : 'unknown time');
      data.status = CasesCache[$(this).attr('caseid')].status.sort(function (a, b) {
        return a.date < b.date;
      });
      data.status = $.map(data.status, function (n, idx) {
        n.invert = idx % 2 == 1;
        n.date = (n.date ? moment.utc(n.date).local().format("MM/DD/YYYY") : "unknown time");
        return n;
      });

      if (data.adjcasestatus && data.adjcasestatus.length > 0) {
        data.oldercases = [];
        data.newercases = [];
        $.each(data.adjcasestatus, function (idx, casestatus) {
          if (idx < 2) {
            data.oldercases.push(casestatus);
          } else {
            data.newercases.push(casestatus);
          }
        });
      }
      var $modal = $('#div_modal');
      $modal.find('.modal-title').html('Case Detail');
      $modal.find('.modal-body').html(Mustache.render($('#detailTpl').html(), data));
      $modal.find('.btn-primary').hide();
      $modal.modal('show').on('shown.bs.modal', function () {
        $modal.css('overflow-y', 'scroll');
      }).on('hidden.bs.modal', function () {
        $modal.css('overflow-y', 'hidden');
      });
    };

    var addFun = function (e) {
      e.preventDefault();
      var $modal = $('#div_modal');
      $modal.find('.modal-title').html('Add Case');
      $modal.find('.modal-body').html(Mustache.render($('#addTpl').html(), {}));
      $modal.find('.btn-primary').text('Add').removeAttr('disabled').unbind('click').bind('click', postCaseFun).show();
      $modal.modal('show');
    };

    var postCaseFun = function (e) {
      e.preventDefault();
      var $number = $('#id_number');
      var $email = $('#id_email');
      var re = /^(([^<>()[\]\\.,;:\s@"]+(\.[^<>()[\]\\.,;:\s@"]+)*)|(".+"))@((\[[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}])|(([a-zA-Z\-0-9]+\.)+[a-zA-Z]{2,}))$/;
      var $this = $(this);
      var $modal = $('#div_modal');
      var is_notify = $('#id_notification').prop('checked');
      $email.parent().removeClass('has-error');

      if (!$number.val()) {
        noty($.extend({}, notyOpt, {text: 'Must input number! ', type: 'error'}));
        return;
      }

      if (is_notify && !$email.val()) {
        noty($.extend({}, notyOpt, {text: 'Must input email! ', type: 'error'}));
        $email.parent().addClass('has-error');
        return;
      }

      if ($email.val() && !re.test($email.val())) {
        noty($.extend({}, notyOpt, {text: 'Must input correct email format! ', type: 'error'}));
        $email.parent().addClass('has-error');
        return;
      }

      $('.spinning').remove();
      $modal.find('.modal-title')
        .append('<span id="spin_span" class="spinning pull-right" style="margin-top:15px;margin-right:' +
        $('#title').width() / 7 + 'px;">Querying your case and adjacent cases.</span>');

      var target = document.getElementById('spin_span');

      var spin = new Spinner({
        lines: 17 // The number of lines to draw
        , length: 0 // The length of each line
        , width: 3 // The line thickness
        , radius: 10 // The radius of the inner circle
        , scale: 1 // Scales overall size of the spinner
        , corners: 1 // Corner roundness (0..1)
        , color: '#000' // #rgb or #rrggbb or array of colors
        , opacity: 0.25 // Opacity of the lines
        , rotate: 38 // The rotation offset
        , direction: 1 // 1: clockwise, -1: counterclockwise
        , speed: 1 // Rounds per second
        , trail: 60 // Afterglow percentage
        , fps: 20 // Frames per second when using setTimeout() as a fallback for CSS
        , zIndex: 2e9 // The z-index (defaults to 2000000000)
        , className: 'spinner' // The CSS class to assign to the spinner
        , top: '35px' // Top position relative to parent
        , left: '90%' // Left position relative to parent
        , shadow: true // Whether to render a shadow
        , hwaccel: false // Whether to use hardware acceleration
        , position: 'absolute' // Element positioning
      }).spin(target);

      $this.attr('disabled', 'true');
      $.ajax({
        'type': 'post',
        'url': '/case/' + $number.val() + '/',
        "data": {'add_email': $email.val(), 'is_notify': is_notify},
        'dataType': 'json'
      }).done(function (data) {
        spin.stop();
        $('.spinning').remove();
        if (data.ok && data.hasOwnProperty('ok')) {
          noty($.extend({}, notyOpt, {text: 'Add case successful!', type: 'success'}));
          setTimeout(getCases, 500);
          $number.parent().removeClass('has-error');
          $modal.find('.btn-primary').unbind('click');
          $modal.modal('hide');
        } else {
          noty($.extend({}, notyOpt, {text: 'Add case fail! ' + data.err, type: 'error'}));
          $this.removeAttr('disabled');
          $number.parent().addClass('has-error');
        }
      });
    };


    $(function () {
      Mustache.tags = ["<%", "%>"];
      Mustache.parse($('#listTpl').html());
      Mustache.parse($('#detailTpl').html());
      Mustache.parse($('#addTpl').html());
      getCases();
      $('#btn_add').bind('click', addFun);
    });

  }
);