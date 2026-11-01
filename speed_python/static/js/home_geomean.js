/* Home page trend of the geometric mean of all benchmarks, one line per
 * configured executable/environment pair (see HOME_GEOMEAN_SERIES).
 *
 * Reads its configuration from data attributes on #geomean-plot:
 *   data-url          JSON endpoint (gethomegeomeandata)
 *   data-changes-url  changes page, used when a point is clicked
 */
(function() {
    var COLORS = ['#4e79a7', '#f28e2b', '#59a14f', '#e15759', '#76b7b2',
                  '#edc948', '#b07aa1', '#ff9da7', '#9c755f', '#bab0ac'];

    function parseDate(s) {
        // "YYYY/MM/DD HH:MM:SS +0000" -> Date (UTC)
        var m = /^(\d+)\/(\d+)\/(\d+) (\d+):(\d+):(\d+)/.exec(s);
        return new Date(Date.UTC(+m[1], m[2] - 1, +m[3], +m[4], +m[5], +m[6]));
    }

    function render(container, data) {
        var series = (data.series || []).filter(function(s) { return s.points.length; });
        if (!series.length) {
            container.innerHTML = '<p class="warning">No results in the last ' +
                                  data.days + ' days.</p>';
            return;
        }

        // Merge all series on a shared time axis; dygraphs wants one row per x.
        var rowsByTime = {};
        var commits = {};  // label -> time -> {commitid, benchmarks}
        series.forEach(function(s, i) {
            commits[s.label] = {};
            s.points.forEach(function(p) {
                var t = parseDate(p[0]).getTime();
                if (!rowsByTime[t]) {
                    rowsByTime[t] = new Array(series.length + 1);
                    rowsByTime[t][0] = new Date(t);
                }
                rowsByTime[t][i + 1] = p[1];
                commits[s.label][t] = {commitid: p[2], benchmarks: p[3]};
            });
        });
        var rows = Object.keys(rowsByTime).sort(function(a, b) { return a - b; })
                         .map(function(t) { return rowsByTime[t]; });
        for (var r = 0; r < rows.length; r++) {
            for (var c = 1; c < rows[r].length; c++) {
                if (rows[r][c] === undefined) { rows[r][c] = null; }
            }
        }

        var labels = ['Date'].concat(series.map(function(s) { return s.label; }));

        new Dygraph(container, rows, {
            labels: labels,
            colors: COLORS.slice(0, series.length),
            connectSeparatedPoints: true,
            drawPoints: true,
            pointSize: 2,
            strokeWidth: 1.5,
            highlightCircleSize: 4,
            legend: 'always',
            labelsDiv: document.getElementById('geomean-legend'),
            labelsSeparateLines: true,
            ylabel: 'Relative to ' + data.days + ' days ago',
            axes: {
                y: { axisLabelFormatter: function(v) { return v.toFixed(2); } }
            },
            valueFormatter: function(v, opts, name, g, row) {
                if (name === 'Date') { return new Date(v).toISOString().slice(0, 16).replace('T', ' '); }
                if (v === null || v === undefined) { return ''; }
                var t = g.getValue(row, 0);
                var c = commits[name] && commits[name][t];
                return v.toFixed(3) + 'x' + (c ? ' (' + c.commitid.slice(0, 10) + ', ' +
                                                   c.benchmarks + ' benchmarks)' : '');
            },
            pointClickCallback: function(e, point) {
                var c = commits[point.name] && commits[point.name][point.xval];
                var s = series.filter(function(x) { return x.label === point.name; })[0];
                if (!c || !s) { return; }
                window.location = container.getAttribute('data-changes-url') +
                    '?rev=' + encodeURIComponent(c.commitid) +
                    '&exe=' + s.executable + '&env=' + s.environment;
            }
        });
    }

    document.addEventListener('DOMContentLoaded', function() {
        var container = document.getElementById('geomean-plot');
        if (!container) { return; }
        var xhr = new XMLHttpRequest();
        xhr.open('GET', container.getAttribute('data-url'));
        xhr.onload = function() {
            if (xhr.status !== 200) {
                container.innerHTML = '<p class="warning">Error retrieving data</p>';
                return;
            }
            render(container, JSON.parse(xhr.responseText));
        };
        xhr.onerror = xhr.onload;
        xhr.send();
    });
})();
