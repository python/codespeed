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

function updateExeColors() {
    $("#executable div.boxbody > ul > ul > li > input").each(function() {
        var $sq = $(this).parent().find("div.seriescolor");
        $sq.css("background-color", $(this).is(':checked') ? getColor($(this).attr("id").slice(10)) : '');
    });
}

function shouldPlotEquidistant() { return $("#equidistant").is(':checked'); }
function shouldPlotQuartiles()   { return $("#show_quartile_bands").is(':checked'); }
function shouldPlotExtrema()     { return $("#show_extrema_bands").is(':checked'); }

function getConfiguration() {
    var config = {
        exe:   readCheckbox("input[name='executable']:checked"),
        base:  $("#baseline option:selected").val(),
        ben:   $("input[name='benchmark']:checked").val(),
        env:   readCheckbox("input[name='environments']:checked"),
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
    $("#plot-legend").remove();
    miniplotInstances.forEach(function(g) { g.destroy(); });
    miniplotInstances = [];
}

// Build dygraphs-ready data from the branches dict.
// Returns {labels, colors, data, commitMap, sortedDateKeys, seriesIds, envIdToIndex}
// Series keys are "exe_id:env_id". Uses customBars: [x, [low,mid,high], ...]
function buildGraphData(branches, environments, median, equidistant) {
    var envIdToIndex = {};
    (environments || []).forEach(function(env, i) { envIdToIndex[String(env.id)] = i; });
    var multiEnv = (environments || []).length > 1;

    var seriesIds = [];  // composite "exe_id:env_id"
    var seriesRaw = {};  // composite -> dateKey -> {low, mid, high, commit, tag}
    var dateIndex = {};  // dateKey -> Date

    for (var branch in branches) {
        for (var compositeKey in branches[branch]) {
            seriesIds.push(compositeKey);
            seriesRaw[compositeKey] = {};
            var pts = branches[branch][compositeKey];
            for (var i = 0; i < pts.length; i++) {
                var pt = pts[i];
                var dateKey = pt[0];
                var mid = pt[1];
                var low, high, commit, tag;

                var suite_version;
                if (median) {
                    // pt: [date, median, max, q3, q1, min, commit, tag, branch, suite_version]
                    var q1  = (pt[4] !== "") ? pt[4] : mid;
                    var q3  = (pt[3] !== "") ? pt[3] : mid;
                    var min = (pt[5] !== "") ? pt[5] : mid;
                    var max = (pt[2] !== "") ? pt[2] : mid;
                    commit = pt[6]; tag = pt[7]; suite_version = pt[9] || '';
                    if (shouldPlotExtrema()) {
                        low = min; high = max;
                    } else if (shouldPlotQuartiles()) {
                        low = q1; high = q3;
                    } else {
                        low = mid; high = mid;
                    }
                } else {
                    // pt: [date, value, std_dev, commit, tag, branch, suite_version]
                    var std = (pt[2] !== "" && pt[2] !== null) ? pt[2] : 0;
                    low = Math.max(0, mid - std);
                    high = mid + std;
                    commit = pt[3]; tag = pt[4]; suite_version = pt[6] || '';
                }

                dateIndex[dateKey] = new Date(dateKey.trim());
                seriesRaw[compositeKey][dateKey] = {low: low, mid: mid, high: high,
                                                    commit: commit, tag: tag,
                                                    suite_version: suite_version,
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
        var ckey = seriesIds[k];
        var kparts = ckey.split(':');
        var exeId = kparts[0];
        var envId = kparts[1] || null;
        var exeLabel = $("label[for*='executable" + exeId + "']").text().trim();
        if (multiEnv && envId) {
            var envObj = (environments || []).reduce(function(found, e) {
                return found || (String(e.id) === envId ? e : null);
            }, null);
            exeLabel = exeLabel + ' (' + (envObj ? envObj.name : envId) + ')';
        }
        labels.push(exeLabel);
        colors.push(getColor(exeId));
    }

    // commitMap[dateKey][compositeKey] = {commit, tag, low, high, suite_version}
    var commitMap = {};
    var tsMap = {}; // timestamp (ms) -> dateKey, for tooltip lookup
    sortedDateKeys.forEach(function(dk) {
        tsMap[dateIndex[dk].getTime()] = dk;
        commitMap[dk] = {};
        seriesIds.forEach(function(ckey) {
            if (seriesRaw[ckey][dk]) {
                var pt = seriesRaw[ckey][dk];
                commitMap[dk][ckey] = {commit: pt.commit, tag: pt.tag,
                                       low: pt.low, high: pt.high,
                                       suite_version: pt.suite_version};
            }
        });
    });

    var graphData = sortedDateKeys.map(function(dk, idx) {
        var xval = equidistant ? idx : dateIndex[dk];
        var row = [xval];
        seriesIds.forEach(function(ckey) {
            var pt = seriesRaw[ckey][dk];
            row.push(pt ? [pt.low, pt.mid, pt.high] : null);
        });
        return row;
    });

    return {labels: labels, colors: colors, data: graphData,
            commitMap: commitMap, sortedDateKeys: sortedDateKeys,
            seriesIds: seriesIds, tsMap: tsMap, dateIndex: dateIndex,
            envIdToIndex: envIdToIndex};
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

    var built = buildGraphData(data.branches, data.environments || [], median, equidistant);
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
    var dateIndex = built.dateIndex;

    // Find x-positions where suite_version changes between adjacent points
    var seen = {};
    var versionBoundaries = [];
    sortedDateKeys.forEach(function(dk, idx) {
        if (idx === 0) { return; }
        var prevDk = sortedDateKeys[idx - 1];
        seriesIds.forEach(function(ckey) {
            var curr = commitMap[dk] && commitMap[dk][ckey];
            var prev = commitMap[prevDk] && commitMap[prevDk][ckey];
            if (curr && prev && curr.suite_version && prev.suite_version &&
                    curr.suite_version !== prev.suite_version && !seen[dk]) {
                seen[dk] = true;
                versionBoundaries.push({dk: dk, idx: idx, label: curr.suite_version});
            }
        });
    });

    // Map label -> color and label -> composite series key for tooltip
    var colorMap = {};
    var labelToSeriesKey = {};
    built.labels.slice(1).forEach(function(lbl, i) {
        colorMap[lbl] = built.colors[i];
        labelToSeriesKey[lbl] = seriesIds[i];
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

        // Collect commit info from the first visible series with data
        var commitInfo = null;
        ld.series.forEach(function(s) {
            if (commitInfo || !s.isVisible || s.y === undefined) { return; }
            var seriesKey = labelToSeriesKey[s.labelHTML] || labelToSeriesKey[s.name];
            if (dk && commitMap[dk] && commitMap[dk][seriesKey]) {
                commitInfo = commitMap[dk][seriesKey];
            }
        });

        var header = '<div style="font-weight:bold;margin-bottom:3px">' +
                     (dk ? dk.slice(0, 16) : '');
        if (commitInfo) {
            header += ' <span style="font-weight:normal;font-size:0.85em;color:#666">commit: ' + commitInfo.commit;
            if (commitInfo.tag) { header += '&nbsp;&nbsp;tag: ' + commitInfo.tag; }
            if (versionBoundaries.length > 0 && commitInfo.suite_version) { header += '&nbsp;&nbsp;suite: ' + commitInfo.suite_version; }
            header += '</span>';
        }
        header += '</div>';

        var html = header;
        ld.series.forEach(function(s) {
            if (!s.isVisible || s.y === undefined) { return; }
            var seriesKey = labelToSeriesKey[s.labelHTML] || labelToSeriesKey[s.name];
            if (!seriesKey) { return; }  // skip baseline
            var color = colorMap[s.labelHTML] || colorMap[s.name] || '#333';
            html += '<div style="margin:2px 0;color:' + color + '">' +
                    '<b>' + s.labelHTML + ': ' + s.y.toPrecision(4) + '</b>';
            if (dk && commitMap[dk] && commitMap[dk][seriesKey]) {
                var info = commitMap[dk][seriesKey];
                if (info.low !== info.high) {
                    html += ' <span style="font-weight:normal">[' +
                            info.low.toPrecision(3) + ' \u2013 ' +
                            info.high.toPrecision(3) + ']</span>';
                }
            }
            html += '</div>';
        });
        return html;
    }

    // Per-series options: baseline gets thinner line; 2nd env gets dashed
    var seriesOpts = {};
    built.labels.slice(1).forEach(function(lbl, i) {
        var isBase = hasBaseline && i === built.labels.length - 2;
        var ckey = built.seriesIds[i] || '';
        var envId = ckey.split(':')[1] || null;
        var envIdx = envId ? (built.envIdToIndex[envId] || 0) : 0;
        seriesOpts[lbl] = {
            strokeWidth: isBase ? 1.5 : 2,
            strokePattern: (!isBase && envIdx === 1) ? [6, 3] : null,
            drawPoints: !isBase,
            pointSize: 3,
            highlightCircleSize: isBase ? 0 : 5,
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

    // When there's a single data point, xMin===xMax and Dygraph clips the dot
    // at the canvas edge. Compute an explicit dateWindow with padding.
    var singlePointWindow = null;
    if (built.data.length === 1) {
        var xVal = equidistant ? built.data[0][0] : built.data[0][0].getTime();
        if (equidistant) {
            singlePointWindow = [xVal - 1, xVal + 1];
        } else {
            var dayMs = 86400000;
            singlePointWindow = [new Date(xVal - dayMs), new Date(xVal + dayMs)];
        }
    }

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
            xRangePad: 20,
            dateWindow: singlePointWindow,
            connectSeparatedPoints: true,
            underlayCallback: function(canvas, area, g) {
                versionBoundaries.forEach(function(b) {
                    var xval = equidistant ? b.idx : dateIndex[b.dk];
                    var cx = g.toDomXCoord(xval);
                    canvas.save();
                    canvas.beginPath();
                    canvas.moveTo(cx, area.y);
                    canvas.lineTo(cx, area.y + area.h);
                    canvas.strokeStyle = 'rgba(120, 120, 120, 0.6)';
                    canvas.lineWidth = 1.5;
                    canvas.setLineDash([4, 3]);
                    canvas.stroke();
                    canvas.setLineDash([]);
                    canvas.fillStyle = 'rgba(80, 80, 80, 0.75)';
                    canvas.font = '10px sans-serif';
                    canvas.fillText(b.label, cx + 3, area.y + 12);
                    canvas.restore();
                });
            },
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
                var highlightedLabel = plotInstance && plotInstance.getHighlightSeries && plotInstance.getHighlightSeries();
                var ckey = (highlightedLabel && labelToSeriesKey[highlightedLabel]) || seriesIds[0];
                var info = commitMap[dk][ckey];
                if (info) {
                    var parts = ckey.split(':');
                    var navEnv = parts[1] || $("input[name='environments']:checked").first().val();
                    window.location = CHANGES_URL + "?rev=" + info.commit +
                                      "&exe=" + parts[0] + "&env=" + navEnv;
                }
            }
        }
    );

    // Persistent legend below the plot
    (function() {
        var $legend = $('<div id="plot-legend" style="margin:6px 0 4px 40px;font-size:0.9em;"></div>');
        built.labels.slice(1).forEach(function(lbl, i) {
            var isBase = hasBaseline && i === built.labels.length - 2;
            var ckey = built.seriesIds[i] || '';
            var envId = ckey.split(':')[1] || null;
            var envIdx = envId ? (built.envIdToIndex[envId] || 0) : 0;
            var color = built.colors[i];
            var dashed = !isBase && envIdx === 1;
            var svg = '<svg width="28" height="12" style="vertical-align:middle;margin-right:3px">' +
                '<line x1="0" y1="6" x2="28" y2="6" stroke="' + color + '" stroke-width="2"' +
                (dashed ? ' stroke-dasharray="6,3"' : '') + '/></svg>';
            $legend.append('<span style="margin-right:16px;white-space:nowrap">' +
                           svg + '<span style="color:' + color + '">' + lbl + '</span></span>');
        });
        $("#plot").after($legend);
    }());

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
    var built = buildGraphData(data.branches, data.environments || [], median, false);
    if (built.data.length === 0) { return; }

    if (data.baseline !== "None") {
        built.labels.push('Baseline');
        built.colors.push(baselineColor);
        var bv = data.baseline[0][1];
        built.data.forEach(function(row) { row.push([bv, bv, bv]); });
    }

    var miniWindow = null;
    if (built.data.length === 1) {
        var mx = built.data[0][0];
        var mxv = (mx instanceof Date) ? mx.getTime() : mx;
        miniWindow = (mx instanceof Date)
            ? [new Date(mxv - 86400000), new Date(mxv + 86400000)]
            : [mxv - 1, mxv + 1];
    }

    var miniSeriesOpts = {};
    built.labels.slice(1).forEach(function(lbl, i) {
        var ckey = built.seriesIds[i] || '';
        var envId = ckey.split(':')[1] || null;
        var envIdx = envId ? (built.envIdToIndex[envId] || 0) : 0;
        miniSeriesOpts[lbl] = {
            strokeWidth: 1.5,
            strokePattern: envIdx === 1 ? [4, 3] : null,
            color: built.colors[i]
        };
    });

    var g = new Dygraph(
        document.getElementById(plotid),
        built.data,
        {
            title: data.benchmark,
            titleHeight: 18,
            labels: built.labels,
            colors: built.colors,
            customBars: true,
            series: miniSeriesOpts,
            legend: 'never',
            axes: {
                x: { drawAxis: false, drawGrid: false },
                y: { drawAxis: false, drawGrid: false, valueRange: [0, null] }
            },
            xRangePad: 20,
            dateWindow: miniWindow,
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
        $("#revisions").val(15).attr("disabled", true);
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
    var benchRadio = $("input:radio[name='benchmark']").filter("[value='" + benchmark + "']");
    if (benchRadio.length === 0 && benchmark !== "grid" && benchmark !== "show_none") {
        // backwards compat: a bare '<name>' permalink defaults to the legacy suite
        benchmark = benchmark + ".legacy";
        benchRadio = $("input:radio[name='benchmark']").filter("[value='" + benchmark + "']");
    }
    benchRadio.prop('checked', true);
    // reveal the suite accordion section that holds the selected benchmark
    benchRadio.closest("ul").show().children("a.togglefold").removeClass('folded');

    var envDefault = (defaults.environments || []).map(String).join(',');
    var envIds = valueOrDefault(params.env, envDefault).split(',').filter(Boolean);
    var envSel = $("input[name='environments']");
    envIds.forEach(function(envId) {
        envSel.filter("[value='" + envId.trim() + "']").prop('checked', true);
    });
    updateEnvIndicators();
    updateExeColors();
    $("#baselinecolor").css("background-color", baselineColor);

    $("#equidistant").prop('checked', valueOrDefault(params.equid, defaults.equidistant) === "on");
    $("#show_quartile_bands").prop('checked', valueOrDefault(params.quarts, defaults.quartiles) === "on");
    $("#show_extrema_bands").prop('checked', valueOrDefault(params.extr, defaults.extrema) === "on");
}

function updateEnvIndicators() {
    $("input[name='environments']").each(function() {
        $(this).siblings('.envlinecolor').text('');
    });
    $("input[name='environments']:checked").each(function(i) {
        $(this).siblings('.envlinecolor').text(i === 0 ? '───' : '╌╌╌');
    });
}

function initializeSite() {
    var params = getUrlParams();
    setExeColors();
    setValuesOfInputFields(params);

    var onChange = function() { updateUrl(); refreshContent(); };

    $("#revisions, #baseline").change(onChange);
    $("input[name='branch'], input[name='benchmark']," +
      "#equidistant, #show_quartile_bands, #show_extrema_bands"
    ).change(onChange);
    $("input[name='executable']").change(function() { updateExeColors(); onChange(); });
    $("input[name='environments']").change(function() {
        if ($("input[name='environments']:checked").length > 2) {
            $(this).prop('checked', false);
            return;
        }
        updateEnvIndicators();
        onChange();
    });
    $('.checkall, .uncheckall').click(function() { updateExeColors(); onChange(); });

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
    if (!defaults.environments) {
        defaults.environments = defaults.environment ? [defaults.environment] : [];
    }
    $.ajaxSetup({cache: false});
    initializeSite();
}

return { init: init };

})(window);
