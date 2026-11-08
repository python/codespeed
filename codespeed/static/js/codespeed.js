function readCheckbox(el) {
    /* Builds a string that holds all checked values in an input form */
    var config = "";
    $(el).each(function() {
        config += $(this).val() + ",";
    });
    // Remove last comma
    config = config.slice(0, -1);
    return config;
}

function getLoadText(text, h) {
    var loadtext = '<div style="text-align:center;">';
    var pstyle = "";
    if (h > 0) {
        h = h - 32;
        if(h < 80) { h = 180; }
        else if (h > 400) { h = 400; }
        pstyle = ' style="line-height:' + h + 'px;"';
    }
    loadtext += '<p' + pstyle + '>'+ text;
    loadtext += '</p></div>';
    return loadtext;
}

$(function() {
    // Check all and none links
    $('.checkall').each(function() {
        var inputs = $(this).closest("ul").children("li").children("input");
        $(this).click(function() {
            inputs.prop("checked", true);
            return false;
        });
    });

    $('.uncheckall').each(function() {
        var inputs = $(this).closest("ul").children("li").children("input");
        $(this).click(function() {
            inputs.prop("checked", false);
            return false;
        });
    });

    $('.togglefold').each(function() {
        var lis = $(this).parent().children("li");
        // count radios too (timeline groups use radio inputs, comparison checkboxes)
        var allUnchecked = lis.find("input").filter(':checked').length === 0;
        if (allUnchecked) {
            lis.hide();
            $(this).addClass('folded');
        }
        $(this).click(function() {
            lis.slideToggle();
            $(this).toggleClass('folded');
            return false;
        });
    });
});

/* Colour theme.
 *
 * base.html sets data-theme on <html> before first paint. This keeps it in
 * step with the header toggle, the choice stored in localStorage, the OS
 * setting (followed until the user picks one) and other tabs, and tells the
 * chart scripts when to redraw: canvas charts cannot read the stylesheet.
 */
var Theme = (function() {
    var STORAGE_KEY = 'codespeed-theme';
    var root = document.documentElement;
    var listeners = [];
    var osDark = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;

    function current() {
        return root.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
    }

    function stored() {
        var value = null;
        try { value = localStorage.getItem(STORAGE_KEY); } catch (e) {}
        return (value === 'light' || value === 'dark') ? value : null;
    }

    function updateButton() {
        var label = 'Switch to ' + (current() === 'dark' ? 'light' : 'dark') + ' theme';
        $('#theme-toggle').attr({'aria-label': label, title: label});
    }

    function apply(theme) {
        if (theme === current()) { return; }
        root.setAttribute('data-theme', theme);
        updateButton();
        listeners.forEach(function(fn) { fn(theme); });
    }

    // The colours a canvas chart needs, resolved from the stylesheet's tokens
    function chartColors() {
        var style = getComputedStyle(root);
        function token(name, fallback) {
            return style.getPropertyValue(name).trim() || fallback;
        }
        return {
            text: token('--chart-text', '#666'),
            grid: token('--chart-grid', 'rgba(0, 0, 0, 0.1)'),
            faint: token('--text-faint', '#aaa'),
            surface: token('--surface', '#fff')
        };
    }

    // Dygraphs options for the parts it draws on the canvas. Hovering a
    // series fades the others by painting the plot with the highlight
    // background, which defaults to white, so it must match the surface.
    function dygraphOptions() {
        var colors = chartColors();
        return {
            axisLineColor: colors.text,
            gridLineColor: colors.grid,
            gridLineWidth: 1,
            highlightSeriesBackgroundColor: colors.surface
        };
    }

    $(function() {
        updateButton();
        $('#theme-toggle').click(function() {
            var next = current() === 'dark' ? 'light' : 'dark';
            try { localStorage.setItem(STORAGE_KEY, next); } catch (e) {}
            apply(next);
        });
        if (osDark && osDark.addEventListener) {
            osDark.addEventListener('change', function(e) {
                if (!stored()) { apply(e.matches ? 'dark' : 'light'); }
            });
        }
        // A toggle in another tab of the site
        window.addEventListener('storage', function(e) {
            if (e.key === STORAGE_KEY && stored()) { apply(stored()); }
        });
    });

    return {
        current: current,
        chartColors: chartColors,
        dygraphOptions: dygraphOptions,
        onChange: function(fn) { listeners.push(fn); }
    };
})();
