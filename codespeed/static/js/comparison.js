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

function getConfiguration() {
  return {
    exe: readCheckbox("input[name='executables']:checked"),
    ben: readCheckbox("input[name='benchmarks']:checked"),
    env: readCheckbox("input[name='environments']:checked"),
    hor: $("input[name='direction']").is(':checked'),
    bas: $("#baseline option:selected").val(),
    chart: $("#chart_type option:selected").val()
  };
}

function refreshContent() {
  var conf = getConfiguration(),
      exes = conf.exe.split(","),
      bens  = conf.ben.split(","),
      enviros = conf.env.split(","),
      msg = "";

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

  chartInstances.forEach(function(c) { c.destroy(); });
  chartInstances = [];
  $("#plotwrapper").fadeOut("fast", function() {
    $(this).html(msg).show();
    var plotcounter = 1;
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
      renderComparisonPlot(plotid, unit, benchmarks, exes, enviros, conf.bas, conf.chart, conf.hor);
    }
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
  $("input[name='executables']:checked").each(function() {
    var key = $(this).val();
    var name = $(this).next('label').text().trim();
    $baseline.append($('<option>').val(key).text(name));
  });
  if ($baseline.find("option[value='" + current + "']").length) {
    $baseline.val(current);
  } else {
    $baseline.val('none');
  }
}

function loadData() {
  var conf = getConfiguration();
  if (!conf.exe || !conf.ben) {
    // Nothing to fetch: clear any previous chart and show the warning
    chartInstances.forEach(function(c) { c.destroy(); });
    chartInstances = [];
    refreshContent();
    return;
  }
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
    var baselineLabel = baseline !== "none" ? $("label[for='exe_" + baseline + "']").text().trim() : "";

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
                var exeLabel = $("label[for='exe_" + exes[i] + "']").text().trim();
                if (chart === "relative bars" && exes[i] === baseline) { continue; }
                var data = [];
                for (var b = 0; b < benchmarks.length; b++) {
                    var val = compdata[exes[i]] && compdata[exes[i]][enviros[j]]
                        ? compdata[exes[i]][enviros[j]][benchmarks[b]]
                        : null;
                    if (val !== null && baseline !== "none") {
                        var baseval = compdata[baseline] && compdata[baseline][enviros[j]]
                            ? compdata[baseline][enviros[j]][benchmarks[b]]
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
                var exeLabel = $("label[for='exe_" + exes[i] + "']").text().trim();
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
                        var baseval = compdata[baseline] && compdata[baseline][enviros[j]]
                            ? compdata[baseline][enviros[j]][benchmarks[b]]
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
                title: {display: true, text: title, font: {size: 15}},
                tooltip: {position: 'cursor'},
                legend: {
                    position: 'right',
                    align: 'start',
                    labels: {
                        font: {size: FONT_SIZE},
                        boxWidth: 20,
                        boxHeight: FONT_SIZE,
                        padding: 8
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
}

function init(defaults) {
    bench_units = defaults.bench_units;

    // Set default values
    $("#chart_type").val(defaults.chart_type);
    $("#direction").prop('checked', defaults.direction === "True");

    var sel = $("input[name='executables']");
    $.each(defaults.executables, function(i, exe) {
        sel.filter("[value='" + exe + "']").prop('checked', true);
    });

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
    $("#chart_type, #baseline, #direction, input[name='environments']").change(refreshContent);

    $.ajaxSetup ({
      cache: false
    });

    loadData();

    $("#permalink").click(function() {
        window.location = "?" + $.param(getConfiguration());
    });
}

return {
    init: init
};

})(window);
