var Timeline = (function(window){

var CHANGES_URL = window.CHANGES_URL,
    readCheckbox = window.readCheckbox,
    getLoadText = window.getLoadText;

var baselineColor = "#d8b83f",
    seriesColors = ["#4bb2c5", "#EAA228", "#579575", "#953579", "#839557",
                    "#ff5800", "#958c12", "#4b5de4", "#0085cc"],
    defaults,
    plotInstance = null,
    miniplotInstances = [];

function setExeColors() {
    $("#executable > div.boxbody > ul > ul > li > input").each(function(index) {
        $(this).data('color', seriesColors[index % seriesColors.length]);
    });
}

function getColor(exe_id) {
    return $("#executable > div.boxbody").find("input[value='" + exe_id + "']").data('color');
}

function shouldPlotEquidistant() { return $("#equidistant").is(':checked'); }
function shouldPlotQuartiles()   { return $("#show_quartile_bands").is(':checked'); }
function shouldPlotExtrema()     { return $("#show_extrema_bands").is(':checked'); }

function getConfiguration() {
    var config = {
        exe:   readCheckbox("input[name='executable']:checked"),
        base:  $("#baseline option:selected").val(),
        ben:   $("input[name='benchmark']:checked").val(),
        env:   $("input[name='environments']:checked").val(),
        revs:  $("#revisions option:selected").val(),
        equid: shouldPlotEquidistant() ? "on" : "off",
        quarts: shouldPlotQuartiles() ? "on" : "off",
        extr:  shouldPlotExtrema() ? "on" : "off"
    };
    var branch = readCheckbox("input[name='branch']:checked");
    if (branch) { config.bran = branch; }
    return config;
}

function getUrlParams() {
    var params = {};
    var search = window.location.search.substring(1) || window.location.hash.replace(/^#\/?/, '');
    search.split('&').forEach(function(part) {
        if (!part) { return; }
        var eq = part.indexOf('=');
        var key = decodeURIComponent(part.slice(0, eq));
        var val = decodeURIComponent(part.slice(eq + 1).replace(/\+/g, ' '));
        params[key] = val;
    });
    return params;
}

function updateUrl() {
    history.replaceState(null, '', '?' + $.param(getConfiguration()));
}

function destroyPlots() {
    if (plotInstance) { plotInstance.destroy(); plotInstance = null; }
    $("#plot").off("mousemove.tooltip");
    miniplotInstances.forEach(function(g) { g.destroy(); });
    miniplotInstances = [];
}

// Build dygraphs-ready data from the branches dict.
// Returns {labels, colors, data, commitMap, sortedDateKeys, seriesIds}
// Uses customBars: data rows are [x, [low,mid,high], [low,mid,high], ...]
function buildGraphData(branches, median, equidistant) {
    var seriesIds = [];
    var seriesRaw = {};  // exe_id -> dateKey -> {low, mid, high, commit, tag}
    var dateIndex = {};  // dateKey -> Date

    for (var branch in branches) {
        for (var exe_id in branches[branch]) {
            seriesIds.push(exe_id);
            seriesRaw[exe_id] = {};
            var pts = branches[branch][exe_id];
            for (var i = 0; i < pts.length; i++) {
                var pt = pts[i];
                var dateKey = pt[0];
                var mid = pt[1];
                var low, high, commit, tag;

                if (median) {
                    // pt: [date, median, max, q3, q1, min, commit, tag, branch]
                    var q1  = (pt[4] !== "") ? pt[4] : mid;
                    var q3  = (pt[3] !== "") ? pt[3] : mid;
                    var min = (pt[5] !== "") ? pt[5] : mid;
                    var max = (pt[2] !== "") ? pt[2] : mid;
                    commit = pt[6]; tag = pt[7];
                    if (shouldPlotExtrema()) {
                        low = min; high = max;
                    } else if (shouldPlotQuartiles()) {
                        low = q1; high = q3;
                    } else {
                        low = mid; high = mid;
                    }
                } else {
                    // pt: [date, value, std_dev, commit, tag, branch]
                    var std = (pt[2] !== "" && pt[2] !== null) ? pt[2] : 0;
                    low = Math.max(0, mid - std);
                    high = mid + std;
                    commit = pt[3]; tag = pt[4];
                }

                dateIndex[dateKey] = new Date(dateKey.trim());
                seriesRaw[exe_id][dateKey] = {low: low, mid: mid, high: high,
                                              commit: commit, tag: tag,
                                              dateKey: dateKey};
            }
        }
    }

    var sortedDateKeys = Object.keys(dateIndex).sort(function(a, b) {
        return dateIndex[a] - dateIndex[b];
    });

    var labels = ['Date'];
    var colors = [];
    for (var k = 0; k < seriesIds.length; k++) {
        var id = seriesIds[k];
        labels.push($("label[for*='executable" + id + "']").text().trim());
        colors.push(getColor(id));
    }

    // commitMap[dateKey][exe_id] = {commit, tag}
    var commitMap = {};
    var tsMap = {}; // timestamp (ms) -> dateKey, for legend lookup
    sortedDateKeys.forEach(function(dk) {
        tsMap[dateIndex[dk].getTime()] = dk;
        commitMap[dk] = {};
        seriesIds.forEach(function(id) {
            if (seriesRaw[id][dk]) {
                var pt = seriesRaw[id][dk];
                commitMap[dk][id] = {commit: pt.commit, tag: pt.tag,
                                     low: pt.low, high: pt.high};
            }
        });
    });

    var graphData = sortedDateKeys.map(function(dk, idx) {
        var xval = equidistant ? idx : dateIndex[dk];
        var row = [xval];
        seriesIds.forEach(function(id) {
            var pt = seriesRaw[id][dk];
            row.push(pt ? [pt.low, pt.mid, pt.high] : null);
        });
        return row;
    });

    return {labels: labels, colors: colors, data: graphData,
            commitMap: commitMap, sortedDateKeys: sortedDateKeys,
            seriesIds: seriesIds, tsMap: tsMap};
}

function renderPlot(data) {
    var median = data['data_type'] === 'M';
    var equidistant = shouldPlotEquidistant();

    $("#plotgrid").html('<div id="plot" style="width:100%;height:420px;"></div>');
    if (data.benchmark_description) {
        $("#plotdescription").html(
            '<p class="note"><i>' + data.benchmark + '</i>: ' + data.benchmark_description + '</p>');
    }

    if (median) {
        $("span.options.median").css("display", "inline");
    }

    var built = buildGraphData(data.branches, median, equidistant);
    if (built.data.length === 0) {
        $("#plot").html(getLoadText("No data available", 420));
        return;
    }

    // Add baseline as an extra series (no band — flat line)
    var hasBaseline = data.baseline !== "None";
    if (hasBaseline) {
        var baselineLabel = $("#baseline option:selected").text().trim();
        built.labels.push(baselineLabel);
        built.colors.push(baselineColor);
        var baselineVal = data.baseline[0][1];
        built.data.forEach(function(row) {
            row.push([baselineVal, baselineVal, baselineVal]);
        });
    }

    var commitMap = built.commitMap;
    var sortedDateKeys = built.sortedDateKeys;
    var seriesIds = built.seriesIds;
    var tsMap = built.tsMap;
    var env = $("input[name='environments']:checked").val();

    // Map label -> color and label -> exeId for tooltip
    var colorMap = {};
    var labelToExeId = {};
    built.labels.slice(1).forEach(function(lbl, i) {
        colorMap[lbl] = built.colors[i];
        labelToExeId[lbl] = seriesIds[i];
    });

    function lookupDateKey(x) {
        if (equidistant) { return sortedDateKeys[Math.round(x)]; }
        var dk = tsMap[x];
        if (!dk) {
            // find closest
            dk = sortedDateKeys.reduce(function(best, curr) {
                return Math.abs(new Date(curr.trim()) - x) <
                       Math.abs(new Date(best.trim()) - x) ? curr : best;
            }, sortedDateKeys[0]);
        }
        return dk;
    }

    function legendFormatter(ld) {
        if (ld.x === undefined) { return ''; }
        var dk = lookupDateKey(ld.x);
        var html = '<div style="font-weight:bold;margin-bottom:3px">' +
                   (dk ? dk.slice(0, 16) : '') + '</div>';
        ld.series.forEach(function(s) {
            if (!s.isVisible || s.y === undefined) { return; }
            var exeId = labelToExeId[s.labelHTML] || labelToExeId[s.name];
            var color = colorMap[s.labelHTML] || colorMap[s.name] || '#333';
            html += '<div style="margin:2px 0;color:' + color + '">' +
                    '<b>' + s.labelHTML + ': ' + s.y.toPrecision(4) + '</b>';
            if (dk && commitMap[dk] && commitMap[dk][exeId]) {
                var info = commitMap[dk][exeId];
                if (info.low !== info.high) {
                    html += ' <span style="font-weight:normal">[' +
                            info.low.toPrecision(3) + ' \u2013 ' +
                            info.high.toPrecision(3) + ']</span>';
                }
                html += '<br><span style="font-size:0.85em;font-weight:normal;color:#666">' +
                        'commit: ' + info.commit;
                if (info.tag) { html += '&nbsp;&nbsp;tag: ' + info.tag; }
                html += '</span>';
            }
            html += '</div>';
        });
        return html;
    }

    // Per-series options: baseline gets thinner line, no points
    var seriesOpts = {};
    built.labels.slice(1).forEach(function(lbl, i) {
        var isBase = hasBaseline && i === built.labels.length - 2;
        seriesOpts[lbl] = {
            strokeWidth: isBase ? 1.5 : 2,
            drawPoints: !isBase,
            pointSize: 3,
            color: built.colors[i]
        };
    });

    var xAxisOpts = equidistant ? {
        axisLabelFormatter: function(idx) {
            var dk = sortedDateKeys[Math.round(idx)];
            return dk ? dk.slice(0, 10) : '';
        },
        valueFormatter: function(idx) {
            var dk = sortedDateKeys[Math.round(idx)];
            return dk ? dk.slice(0, 10) : '';
        }
    } : {};

    var lastHighlightPoints = null, lastHighlightX = null;

    plotInstance = new Dygraph(
        document.getElementById('plot'),
        built.data,
        {
            title: data.benchmark,
            titleHeight: 24,
            labels: built.labels,
            colors: built.colors,
            customBars: true,
            series: seriesOpts,
            legend: 'never',
            ylabel: data.units + data.lessisbetter,
            axes: {
                x: xAxisOpts,
                y: { valueRange: [0, null] }
            },
            connectSeparatedPoints: true,
            highlightSeriesOpts: { strokeWidth: 3 },
            highlightCircleSize: 5,
            highlightCallback: function(e, x, points) {
                lastHighlightX = x;
                lastHighlightPoints = points;
            },
            unhighlightCallback: function() {
                lastHighlightPoints = null;
                $("#dygraph-tooltip").hide();
            },
            // Navigate to changes page on point click
            clickCallback: function(e, x, points) {
                var dk;
                if (equidistant) {
                    dk = sortedDateKeys[Math.round(x)];
                } else {
                    dk = sortedDateKeys.reduce(function(best, curr) {
                        return Math.abs(new Date(curr.trim()) - x) <
                               Math.abs(new Date(best.trim()) - x) ? curr : best;
                    }, sortedDateKeys[0]);
                }
                if (!dk || !commitMap[dk]) { return; }
                var id = seriesIds[0];
                var info = commitMap[dk][id];
                if (info) {
                    window.location = CHANGES_URL + "?rev=" + info.commit +
                                      "&exe=" + id + "&env=" + env;
                }
            }
        }
    );

    $("#plot").on("mousemove.tooltip", function(e) {
        var $tip = $("#dygraph-tooltip");
        if (!lastHighlightPoints) { $tip.hide(); return; }
        var THRESHOLD = 0.015;
        var area = plotInstance.getArea();
        var mx = e.offsetX !== undefined ? e.offsetX : e.layerX;
        var my = e.offsetY !== undefined ? e.offsetY : e.layerY;
        var close = lastHighlightPoints.some(function(pt) {
            if (pt.canvasx === undefined) { return false; }
            var dx = (mx - pt.canvasx) / area.w;
            var dy = (my - pt.canvasy) / area.w;
            return Math.sqrt(dx*dx + dy*dy) < THRESHOLD;
        });
        if (close) {
            var chartOffset = $("#plot").offset();
            var absX = chartOffset.left + mx;
            var onRight = absX > $(window).width() / 2;
            $tip.html(legendFormatter({x: lastHighlightX, series: lastHighlightPoints.map(function(pt) {
                return {color: colorMap[pt.name] || '#333',
                        labelHTML: pt.name, name: pt.name,
                        y: pt.yval, isVisible: true};
            })}));
            var tipW = $tip.outerWidth();
            $tip.css({
                left: onRight ? (absX - tipW - 18) + 'px' : (absX + 18) + 'px',
                top:  (chartOffset.top + my - 10) + 'px'
            }).show();
        } else {
            $tip.hide();
        }
    });
}

function renderMiniplot(plotid, data) {
    var median = data['data_type'] === 'M';
    var built = buildGraphData(data.branches, median, false);
    if (built.data.length === 0) { return; }

    if (data.baseline !== "None") {
        built.labels.push('Baseline');
        built.colors.push(baselineColor);
        var bv = data.baseline[0][1];
        built.data.forEach(function(row) { row.push([bv, bv, bv]); });
    }

    var g = new Dygraph(
        document.getElementById(plotid),
        built.data,
        {
            title: data.benchmark,
            titleHeight: 18,
            labels: built.labels,
            colors: built.colors,
            customBars: true,
            legend: 'never',
            axes: {
                x: { drawAxis: false, drawGrid: false },
                y: { drawAxis: false, drawGrid: false, valueRange: [0, null] }
            },
            connectSeparatedPoints: true,
            highlightCircleSize: 0
        }
    );
    miniplotInstances.push(g);
}

function render(data) {
    $("#revisions").attr("disabled", false);
    $("#equidistant").attr("disabled", false);
    $("span.options.median").css("display", "none");

    if (data.first !== false) {
        destroyPlots();
        $("#plotgrid").html("");
        $("#plotdescription").html("");
    }

    if (data.error !== "None") {
        var h = $("#content").height();
        $("#plotgrid").html(getLoadText(data.error, h));
    } else if ($("input[name='benchmark']:checked").val() === "show_none") {
        var h = $("#content").height();
        $("#plotgrid").html(getLoadText("Please select a benchmark on the left", h));
    } else if (data.timelines.length === 0 && data.first !== false) {
        var h = $("#content").height();
        $("#plotgrid").html(getLoadText("No data available", h));
    } else if ($("input[name='benchmark']:checked").val() === "grid") {
        if (data.nextBenchmarks !== false) {
            var config = getConfiguration();
            config.nextBenchmarks = data.nextBenchmarks;
            $.getJSON("json/", config, render);
        }
        $("#revisions").attr("disabled", true);
        $("#equidistant").attr("disabled", true);
        for (var i = 0; i < data.timelines.length; i++) {
            var tl = data.timelines[i];
            var plotid = "plot_" + tl.benchmark_id;
            var $div = $('<div id="' + plotid + '" class="miniplot"></div>');
            $("#plotgrid").append($div);
            $div.click(function() {
                var benchid = $(this).attr("id").slice(5);
                $("#benchmark_" + benchid).prop('checked', true);
                updateUrl();
                refreshContent();
            });
            renderMiniplot(plotid, tl);
        }
    } else {
        renderPlot(data.timelines[0]);
    }
}

function refreshContent() {
    var h = $("#content").height();
    $("#plotgrid").fadeOut("fast", function() {
        $(this).html(getLoadText("Loading...", h)).show();
        $.getJSON("json/", getConfiguration(), render);
    });
}

function valueOrDefault(val, def) {
    return (val !== undefined && val !== '') ? val : def;
}

function setValuesOfInputFields(params) {
    $("input:checkbox").prop('checked', false);

    $("#revisions").val(valueOrDefault(params.revs, defaults.revisions));
    $("#baseline").val(valueOrDefault(params.base, defaults.baseline));

    var executables = params.exe ? params.exe.split(',') : defaults.executables;
    var sel = $("input[name='executable']");
    $.each(executables, function(i, exe) {
        sel.filter("[value='" + exe + "']").prop('checked', true);
    });

    var branches = params.bran ? params.bran.split(',') : defaults.branches;
    sel = $("input[name='branch']");
    $.each(branches, function(i, b) {
        sel.filter("[value='" + b + "']").prop('checked', true);
    });

    var benchmark = valueOrDefault(params.ben, defaults.benchmark);
    $("input:radio[name='benchmark']").filter("[value='" + benchmark + "']").prop('checked', true);

    var environment = valueOrDefault(params.env, defaults.environment);
    $("input:radio[name='environments']").filter("[value='" + environment + "']").prop('checked', true);

    $("#executable div.boxbody > ul > ul > li > input").each(function() {
        $(this).parent().find("div.seriescolor")
            .css("background-color", getColor($(this).attr("id").slice(10)));
    });
    $("#baselinecolor").css("background-color", baselineColor);

    $("#equidistant").prop('checked', valueOrDefault(params.equid, defaults.equidistant) === "on");
    $("#show_quartile_bands").prop('checked', valueOrDefault(params.quarts, defaults.quartiles) === "on");
    $("#show_extrema_bands").prop('checked', valueOrDefault(params.extr, defaults.extrema) === "on");
}

function initializeSite() {
    var params = getUrlParams();
    setValuesOfInputFields(params);
    setExeColors();

    var onChange = function() { updateUrl(); refreshContent(); };

    $("#revisions, #baseline").change(onChange);
    $("input[name='executable'], input[name='branch'], input[name='benchmark']," +
      "input[name='environments'], #equidistant, #show_quartile_bands, #show_extrema_bands"
    ).change(onChange);
    $('.checkall, .uncheckall').click(onChange);

    $("#permalink").click(function() {
        window.location = "?" + $.param(getConfiguration());
    });

    window.addEventListener('popstate', function() {
        setValuesOfInputFields(getUrlParams());
        refreshContent();
    });

    refreshContent();
}

function init(def) {
    defaults = def;
    $.ajaxSetup({cache: false});
    initializeSite();
}

return { init: init };

})(window);
