/* The "Benchmark a pull request" form on the PR Runner tab: offer only this
 * project's executables and the environments that can build the chosen one,
 * and enable "Start run" once there is enough to go on. */
$(function() {
    var form = $('#pr-run-form');
    if (!form.length) { return; }

    function project() {
        return form.find('[name=project]').val();
    }

    function refresh() {
        var executable = form.find('[name=executable]');
        executable.find('option').each(function() {
            var mine = String($(this).data('project')) === String(project());
            $(this).prop('hidden', !mine).prop('disabled', !mine);
        });
        if (executable.find('option:selected').prop('disabled')) {
            executable.val(executable.find('option:not(:disabled)').first().val());
        }
        var chosen = executable.val();
        form.find('[name=runner]').each(function() {
            var offers = String($(this).data('executables')).split(',');
            var able = chosen !== null && $.inArray(String(chosen), offers) !== -1;
            $(this).prop('disabled', !able);
            if (!able) { $(this).prop('checked', false); }
            $(this).closest('label').toggleClass('unavailable', !able);
        });
        var subset = form.find('[name=suite]:checked').val() === 'subset';
        $('#pr-benchmarks').prop('hidden', !subset);
        var ready = $.trim(form.find('[name=pull_request]').val() || '') !== '' &&
            form.find('[name=runner]:checked').length > 0 &&
            (!subset || form.find('[name=benchmark]:checked').length > 0);
        $('#pr-submit').prop('disabled', !ready);
    }

    form.on('change input', 'select, input', refresh);
    $('#pr-benchmark-filter').on('input', function() {
        var needle = $(this).val().toLowerCase();
        $('#pr-benchmarks li').each(function() {
            var name = $(this).find('input').val().toLowerCase();
            $(this).prop('hidden', name.indexOf(needle) === -1);
        });
    });
    form.on('submit', function() {
        $('#pr-submit').prop('disabled', true).text('Queuing\u2026');
    });

    refresh();
});
