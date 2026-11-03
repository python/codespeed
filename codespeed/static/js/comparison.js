
var Comparison = (function(window){

// Localize globals
var readCheckbox = window.readCheckbox, getLoadText = window.getLoadText;

var compdata, bench_units, dataCache = {}, chartInstances = [];

Chart.Tooltip.positioners.cursor = function(_items, eventPosition) {
    return {x: eventPosition.x, y: eventPosition.y};
};

var COLORS = [
    '#4e79a7', '#f28e2b', '#e15759', '#76b7b2',
    '#59a14f', '#edc948', '#b07aa1', '#ff9da7',
    '#9c755f', '#bab0ac'
];
function getColor(i) { return COLORS[i % COLORS.length]; }

function getExeLabel(key) {
    return $("input[name='executables']")
        .filter(function() { return $(this).val() === key; })
        .next('label').text().trim();
}

function getConfiguration() {
  return {
    exe: readCheckbox("input[name='executables']:checked"),
    ben: readCheckbox("input[name='benchmarks']:checked"),
    env: readCheckbox("input[name='environments']:checked"),
    hor: $("input[name='direction']").is(':checked'),
    bas: $("#baseline option:selected").val() || "none",
    chart: $("#chart_type option:selected").val()
  };
}

function updateGraphTitle(exes, enviros, bens, baseline, chart, chartTitles) {
    var $title = $("#graph-title");

    var isPair = (exes.length === 2 && enviros.length === 1) ||
                 (exes.length === 1 && enviros.length === 2);
    if (isPair && chart !== "stacked bars" && compdata) {
        // Resolve which (exe, env) pair is "other" vs "base"
        var otherExe, otherEnv, baselineExe, baselineEnv;

        if (exes.length === 1 && enviros.length === 2) {
            // Same exe, two environments — only show geomean when an explicit baseline env is set
            if (baseline === "none") {
                $title.text(chartTitles.join(' / '));
                return;
            }
            otherExe = exes[0];
            baselineExe = exes[0];
            if (baseline.indexOf('@') !== -1) {
                var bparts = baseline.split('@');
                baselineEnv = bparts[1];
                otherEnv = enviros.filter(function(e) { return e !== baselineEnv; })[0] || enviros[1];
            } else {
                baselineEnv = enviros[0];
                otherEnv = enviros[1];
            }
        } else {
            // Two exes, one environment
            otherEnv = enviros[0];
            baselineEnv = null;
            if (baseline !== "none" && baseline.indexOf('@') !== -1) {
                var bparts = baseline.split('@');
                baselineExe = bparts[0];
                baselineEnv = bparts[1];
            } else if (baseline !== "none") {
                baselineExe = baseline;
            } else {
                baselineExe = exes[0];
            }
            otherExe = exes.filter(function(e) { return e !== baselineExe; })[0];
            if (!otherExe) { otherExe = exes[1]; }
        }

        var envForBase = baselineEnv !== null ? baselineEnv : otherEnv;

        var product = 1, count = 0;
        for (var b = 0; b < bens.length; b++) {
            var val = compdata[otherExe] && compdata[otherExe][otherEnv]
                ? compdata[otherExe][otherEnv][bens[b]]
                : null;
            var baseval = compdata[baselineExe] && compdata[baselineExe][envForBase]
                ? compdata[baselineExe][envForBase][bens[b]]
                : null;
            if (val !== null && baseval !== null && baseval !== 0 && val > 0) {
                product *= val / baseval;
                count++;
            }
        }

        if (count > 0) {
            var geomean = Math.pow(product, 1 / count);

            var lessCount = 0, moreCount = 0;
            var benSet = {};
            for (var b = 0; b < bens.length; b++) { benSet[bens[b]] = true; }
            for (var u in bench_units) {
                var unitBens = bench_units[u][0];
                var unitLess = bench_units[u][1].indexOf("less") !== -1;
                for (var ub = 0; ub < unitBens.length; ub++) {
                    if (benSet[unitBens[ub]]) {
                        if (unitLess) { lessCount++; } else { moreCount++; }
                    }
                }
            }

            var otherLabel = getExeLabel(otherExe);
            var baselineLabel = getExeLabel(baselineExe);
            if (exes.length === 1) {
                otherLabel += ' @ ' + $("label[for='env_" + otherEnv + "']").text().trim();
                baselineLabel += ' @ ' + $("label[for='env_" + envForBase + "']").text().trim();
            } else if (baselineEnv !== null) {
                baselineLabel += ' @ ' + $("label[for='env_" + baselineEnv + "']").text().trim();
            }

            var suffix;
            if (moreCount === 0 && lessCount > 0) {
                suffix = geomean < 1
                    ? ' or <strong>' + (1 / geomean).toFixed(1) + '&times;</strong> faster'
                    : ' or <strong>' + geomean.toFixed(1) + '&times;</strong> slower';
            } else if (lessCount === 0 && moreCount > 0) {
                suffix = geomean > 1
                    ? ' or <strong>' + geomean.toFixed(1) + '&times;</strong> faster'
                    : ' or <strong>' + (1 / geomean).toFixed(1) + '&times;</strong> slower';
            } else {
                suffix = ' relative to baseline';
            }

            $title.html('The geometric average of ' + count + ' benchmarks for <strong>' +
                otherLabel + '</strong> is <strong>' + geomean.toFixed(2) + '</strong>' +
                suffix + ' than the baseline <strong>' + baselineLabel + '</strong>');
            return;
        }
    }

    // Fall back to the chart title(s)
    $title.text(chartTitles.join(' / '));
}

function refreshContent() {
  var conf = getConfiguration(),
      exes = conf.exe.split(","),
      bens  = conf.ben.split(","),
      enviros = conf.env.split(","),
      msg = "";

  $("#graph-title").html("");
  var h = $("#plotwrapper").height();//get height for error message
  if (exes[0] === "") {
    $("#plotwrapper").html('<p class="warning">No executables selected</p>');
    return false;
  } else if (bens[0] === "") {
    $("#plotwrapper").html('<p class="warning">No benchmarks selected</p>');
    return false;
  } else if (enviros[0] === "") {
    $("#plotwrapper").html('<p class="warning">No environments selected</p>');
    return false;
  } else if (conf.chart === "relative bars" && conf.bas === "none") {
    msg = '<p class="warning">For relative bar charts, you must select a baseline to normalize to.</p>';
    $("#plotwrapper").html(msg);
    return false;
  } else if (conf.chart === "stacked bars" &&  conf.bas !== "none") {
      msg = '<p class="warning">Normalized stacked bars actually represent the weighted arithmetic sum, useful to spot which individual benchmarks take up the most time. Choosing different weightings from the "Normalization" menu will change the totals relative to one another. For the correct way to calculate total bars, the geometric mean must be used (see <a href="http://portal.acm.org/citation.cfm?id=5666.5673 " title="How not to lie with statistics: the correct way to summarize benchmark results">paper</a>)</p>';
  }

  if (compdata && compdata.suite_versions) {
    var mismatchedEnvs = enviros.filter(function(envId) {
      var versions = new Set();
      exes.forEach(function(exeKey) {
        var sv = compdata.suite_versions[exeKey];
        if (sv && sv[envId]) {
          sv[envId].forEach(function(v) { versions.add(v); });
        }
      });
      return versions.size > 1;
    });
    if (mismatchedEnvs.length > 0) {
      msg += '<p class="warning">The executables being compared used different benchmark suite versions. Results may not be directly comparable.</p>';
    }
  }

  chartInstances.forEach(function(c) { c.destroy(); });
  chartInstances = [];
  $("#plotwrapper").fadeOut("fast", function() {
    $(this).html(msg).show();
    var plotcounter = 1;
    var chartTitles = [];
    for (var unit in bench_units) {
      var benchmarks = [];
      for (var ben in bens) {
        if ($.inArray(parseInt(bens[ben]), bench_units[unit][0]) !== -1) {
          benchmarks.push(bens[ben]);
        }
      }
      if (benchmarks.length === 0) { continue; }

      var plotid = "plot" + plotcounter;
      $("#plotwrapper").append('<div class="compplot-wrap"><canvas id="' + plotid + '"></canvas></div>');
      plotcounter++;
      var t = renderComparisonPlot(plotid, unit, benchmarks, exes, enviros, conf.bas, conf.chart, conf.hor);
      chartTitles.push(t);
    }
    updateGraphTitle(exes, enviros, bens, conf.bas, conf.chart, chartTitles);
  });
}

function savedata(cacheKey, data) {
  if (data.error !== "None") {
    var h = $("#content").height();//get height for error message
    $("#plotwrapper").html(getLoadText(data.error, h));
    return 1;
  }
  delete data.error;
  dataCache[cacheKey] = data;
  compdata = data;
  refreshContent();
}

function updateBaselineDropdown() {
  var $baseline = $("#baseline");
  var current = $baseline.val();
  $baseline.find("option:not([value='none'])").remove();
  var enviros = readCheckbox("input[name='environments']:checked").split(",").filter(Boolean);
  var multiEnv = enviros.length > 1;
  $("input[name='executables']:checked").each(function() {
    var key = $(this).val();
    var name = $(this).next('label').text().trim();
    if (multiEnv) {
      enviros.forEach(function(envId) {
        var envName = $("label[for='env_" + envId + "']").text().trim();
        $baseline.append($('<option>').val(key + '@' + envId).text(name + ' @ ' + envName));
      });
    } else {
      $baseline.append($('<option>').val(key).text(name));
    }
  });
  if ($baseline.find("option").filter(function() { return $(this).val() === current; }).length) {
    $baseline.val(current);
  } else {
    $baseline.val('none');
  }
}

function loadData() {
  var conf = getConfiguration();
  if (!conf.exe || !conf.ben) { refreshContent(); return; }
  var cacheKey = conf.exe + "|" + conf.ben;
  if (dataCache[cacheKey]) {
    compdata = dataCache[cacheKey];
    refreshContent();
    return;
  }
  var h = $("#content").height();
  $("#plotwrapper").html(getLoadText("Loading...", h));
  $.getJSON("json/", {exe: conf.exe, ben: conf.ben}, function(data) {
    savedata(cacheKey, data);
  });
}

function renderComparisonPlot(plotid, unit, benchmarks, exes, enviros, baseline, chart, horizontal) {
    // baseline may be "exe_key" or "exe_key@env_id" (for cross-env normalization)
    if (!baseline) { baseline = "none"; }
    var baselineExe = baseline, baselineEnv = null;
    if (baseline !== "none" && baseline.indexOf('@') !== -1) {
        var bparts = baseline.split('@');
        baselineExe = bparts[0];
        baselineEnv = bparts[1];
    }

    var baselineLabel = "";
    if (baseline !== "none") {
        baselineLabel = getExeLabel(baselineExe);
        if (baselineEnv !== null) {
            baselineLabel += ' @ ' + $("label[for='env_" + baselineEnv + "']").text().trim();
        }
    }

    var title;
    if (baseline === "none") {
        title = (chart === "stacked bars" ? "Cumulative " : "") + unit;
    } else if (chart === "stacked bars") {
        title = "Cumulative " + unit + " normalized to " + baselineLabel;
    } else if (chart === "relative bars") {
        title = unit + " ratio to " + baselineLabel;
    } else {
        title = unit + " normalized to " + baselineLabel;
    }

    var valueAxisLabel = baseline === "none"
        ? bench_units[unit][2] + bench_units[unit][1]
        : (chart === "relative bars" ? "← worse  |  better →" : "Ratio " + bench_units[unit][1]);

    var datasets = [];
    var labels = [];
    var colorIdx = 0;

    if (chart === "normal bars" || chart === "relative bars") {
        // Labels = benchmark names
        for (var b = 0; b < benchmarks.length; b++) {
            labels.push($("label[for='benchmark_" + benchmarks[b] + "']").text().trim());
        }
        for (var i = 0; i < exes.length; i++) {
            for (var j = 0; j < enviros.length; j++) {
                var exeLabel = getExeLabel(exes[i]);
                if (chart === "relative bars" && exes[i] === baselineExe &&
                        (baselineEnv === null || baselineEnv === enviros[j])) { continue; }
                var data = [];
                for (var b = 0; b < benchmarks.length; b++) {
                    var val = compdata[exes[i]] && compdata[exes[i]][enviros[j]]
                        ? compdata[exes[i]][enviros[j]][benchmarks[b]]
                        : null;
                    if (val !== null && baseline !== "none") {
                        var envForBase = baselineEnv !== null ? baselineEnv : enviros[j];
                        var baseval = compdata[baselineExe] && compdata[baselineExe][envForBase]
                            ? compdata[baselineExe][envForBase][benchmarks[b]]
                            : null;
                        val = (baseval === null || baseval === 0) ? null : val / baseval;
                    }
                    data.push(val);
                }
                var color = getColor(colorIdx++);
                datasets.push({
                    label: exeLabel + (enviros.length > 1 ? " @ " + $("label[for='env_" + enviros[j] + "']").text().trim() : ""),
                    data: data,
                    backgroundColor: color,
                    borderColor: color,
                    borderWidth: 1
                });
            }
        }
    } else if (chart === "stacked bars") {
        // Labels = exe@env names
        for (var i = 0; i < exes.length; i++) {
            for (var j = 0; j < enviros.length; j++) {
                var exeLabel = getExeLabel(exes[i]);
                labels.push(exeLabel + (enviros.length > 1 ? " @ " + $("label[for='env_" + enviros[j] + "']").text().trim() : ""));
            }
        }
        for (var b = 0; b < benchmarks.length; b++) {
            var benchLabel = $("label[for='benchmark_" + benchmarks[b] + "']").text().trim();
            var data = [];
            for (var i = 0; i < exes.length; i++) {
                for (var j = 0; j < enviros.length; j++) {
                    var val = compdata[exes[i]] && compdata[exes[i]][enviros[j]]
                        ? compdata[exes[i]][enviros[j]][benchmarks[b]]
                        : null;
                    if (val !== null && baseline !== "none") {
                        var envForBase = baselineEnv !== null ? baselineEnv : enviros[j];
                        var baseval = compdata[baselineExe] && compdata[baselineExe][envForBase]
                            ? compdata[baselineExe][envForBase][benchmarks[b]]
                            : null;
                        val = (baseval === null || baseval === 0) ? null : val / baseval;
                    }
                    data.push(val);
                }
            }
            var color = getColor(colorIdx++);
            datasets.push({label: benchLabel, data: data, backgroundColor: color, borderColor: color, borderWidth: 1});
        }
    }

    if (datasets.length === 0) { return; }

    // Mark datasets where all values are null (baseline has no data for that env)
    datasets.forEach(function(ds) {
        ds.allNull = ds.data.every(function(v) { return v === null; });
    });

    // Size the container
    var wrapWidth = $("#plotwrapper").width();
    var h = horizontal
        ? Math.min(2000, Math.max(300, labels.length * datasets.length * 22 + 100))
        : 400;
    var wrap = $("#" + plotid).parent();
    wrap.css({width: wrapWidth, height: h, marginBottom: '20px'});

    var isStacked = chart === "stacked bars";
    var indexAxis = horizontal ? 'y' : 'x';
    var valueAxis = horizontal ? 'x' : 'y';

    var FONT_SIZE = 13;
    var scaleValue = {
        stacked: isStacked,
        title: {display: true, text: valueAxisLabel, font: {size: FONT_SIZE}},
        ticks: {font: {size: FONT_SIZE}},
        min: (chart === "relative bars") ? undefined : 0
    };
    var scaleIndex = {
        stacked: isStacked,
        ticks: {autoSkip: false, font: {size: FONT_SIZE}}
    };

    var ctx = document.getElementById(plotid);
    var instance = new Chart(ctx, {
        type: 'bar',
        data: {labels: labels, datasets: datasets},
        options: {
            indexAxis: indexAxis,
            animation: false,
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                title: {display: false},
                tooltip: {position: 'cursor'},
                legend: {
                    position: 'right',
                    align: 'start',
                    labels: {
                        font: {size: FONT_SIZE},
                        boxWidth: 20,
                        boxHeight: FONT_SIZE,
                        padding: 8,
                        generateLabels: function(chart) {
                            var items = Chart.defaults.plugins.legend.labels.generateLabels(chart);
                            items.forEach(function(item) {
                                var ds = chart.data.datasets[item.datasetIndex];
                                if (ds && ds.allNull) {
                                    // Apply unicode combining strikethrough to each character
                                    item.text = item.text.split('').join('\u0336') + '\u0336';
                                    item.fontColor = '#aaa';
                                }
                            });
                            return items;
                        }
                    }
                }
            },
            scales: {
                [valueAxis]: scaleValue,
                [indexAxis]: scaleIndex
            }
        }
    });
    chartInstances.push(instance);
    return title;
}

function init(defaults) {
    bench_units = defaults.bench_units;

    // Set default values
    $("#chart_type").val(defaults.chart_type);
    $("#direction").prop('checked', defaults.direction === "True");

    /*
    var sel = $("input[name='executables']");
    $.each(defaults.executables, function(i, exe) {
        sel.filter("[value='" + exe + "']").prop('checked', true);
    });
    */

    sel = $("input[name='environments']");
    $.each(defaults.environments, function(i, env) {
        sel.filter("[value='" + env + "']").prop('checked', true);
    });

    // Populate baseline dropdown from initially-checked executables
    updateBaselineDropdown();
    $("#baseline").val(defaults.baseline);

    // Exe changes: rebuild baseline dropdown + re-fetch
    $("input[name='executables']").change(function() {
        updateBaselineDropdown();
        loadData();
    });
    $("#executable .checkall, #executable .uncheckall").click(function() {
        updateBaselineDropdown();
        loadData();
    });

    // Benchmark changes: re-fetch only
    $("input[name='benchmarks']").change(loadData);
    $("#benchmark .checkall, #benchmark .uncheckall").click(loadData);

    // Re-render without re-fetching for other controls
    $("#chart_type, #baseline, #direction").change(refreshContent);
    $("input[name='environments']").change(function() {
        updateBaselineDropdown();
        refreshContent();
    });

    $.ajaxSetup ({
      cache: false
    });

    loadData();

    $("#permalink").click(function() {
        var conf = getConfiguration();
        var $all = $("input[name='benchmarks']");
        var $checked = $("input[name='benchmarks']:checked");
        if ($all.length > 0 && $all.length === $checked.length) {
            conf.ben = 'all';
        } else {
            // Tally checked vs total per source
            var sources = {};
            $all.each(function() {
                var src = $(this).data('source');
                if (!sources[src]) { sources[src] = {total: 0, checked: 0}; }
                sources[src].total++;
                if ($(this).is(':checked')) { sources[src].checked++; }
            });
            var full = Object.keys(sources).filter(function(s) {
                return sources[s].checked === sources[s].total;
            });
            var empty = Object.keys(sources).filter(function(s) {
                return sources[s].checked === 0;
            });
            // Use source aliases only when every source is either fully selected or fully empty
            if (full.length + empty.length === Object.keys(sources).length && full.length > 0) {
                conf.ben = full.join(',');
            }
        }
        var qs = Object.keys(conf).map(function(k) {
            return k + '=' + encodeURIComponent(String(conf[k]))
                .replace(/%2C/gi, ',')
                .replace(/%3A/gi, ':')
                .replace(/%40/gi, '@')
                .replace(/%20/g, '+');
        }).join('&');
        window.location = '?' + qs;
    });

    $("#exportcsv").click(function(e) {
        e.preventDefault();
        if (!compdata) { return; }
        var conf = getConfiguration();
        var exes = conf.exe ? conf.exe.split(",").filter(Boolean) : [];
        var enviros = readCheckbox("input[name='environments']:checked").split(",").filter(Boolean);
        var benchmarks = conf.ben ? conf.ben.split(",").filter(Boolean) : [];

        // Header row: benchmark, then one column per exe@env
        var header = ["benchmark"];
        for (var i = 0; i < exes.length; i++) {
            for (var j = 0; j < enviros.length; j++) {
                var exeLabel = getExeLabel(exes[i]);
                var envLabel = $("label[for='env_" + enviros[j] + "']").text().trim();
                header.push(enviros.length > 1 ? exeLabel + "@" + envLabel : exeLabel);
            }
        }

        var rows = [header];
        for (var b = 0; b < benchmarks.length; b++) {
            var benchLabel = $("label[for='benchmark_" + benchmarks[b] + "']").text().trim();
            var row = [benchLabel];
            for (var i = 0; i < exes.length; i++) {
                for (var j = 0; j < enviros.length; j++) {
                    var val = compdata[exes[i]] && compdata[exes[i]][enviros[j]]
                        ? compdata[exes[i]][enviros[j]][benchmarks[b]]
                        : "";
                    row.push(val === null || val === undefined ? "" : val);
                }
            }
            rows.push(row);
        }

        var csv = rows.map(function(r) { return r.join(","); }).join("\n");
        var blob = new Blob([csv], {type: "text/csv"});
        var url = URL.createObjectURL(blob);
        var a = document.createElement("a");
        a.href = url;
        a.download = "comparison.csv";
        a.click();
        URL.revokeObjectURL(url);
    });
}

return {
    init: init
};

})(window);
