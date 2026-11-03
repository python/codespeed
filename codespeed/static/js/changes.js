var Changes = (function(window){

// Localize globals
var TIMELINE_URL = window.TIMELINE_URL, getLoadText = window.getLoadText;

var currentproject, changethres, trendthres, projectmatrix, revisionboxes = {}, revisiondata = {}, envhasresults = {};

function getConfiguration(revision) {
    return {
        tre: $("#trend option:selected").val(),
        rev: revision || $("#revision option:selected").val(),
        exe: $("input[name='executable']:checked").val(),
        env: $("input[name='environment']:checked").val()
    };
}

function permalinkToTimeline(benchmark, environment) {
    window.location=window.TIMELINE_URL + "?ben=" + benchmark + "&env=" + environment;
}

//colors number based on a threshold
function getColorcode(change, theigh, tlow) {
    if (change < tlow) { return "status-red"; }
    else if (change > theigh) { return "status-green"; }
    else { return "status-node"; }
}

function colorTable() {
    //color two colums to the right starting with index = last-1
    // Each because there is one table per units type
    $(".tablesorter").each(function() {
        // Find column index of the current change column (one before last)
        var index = $(this).find("thead tr th").length - 2;
        var lessisbetter = $(this).data("lessisbetter");

        $(this).find(":not(thead) > tr").each(function() {
            var change = $(this).data("change"),
                trend = $(this).data("trend");

            // Check whether less is better
            if (lessisbetter === "False") {
                change = -change;
                trend = -trend;
            }
            //Color change column
            $(this).children("td:eq("+index+")").addClass(getColorcode(-change, changethres, -changethres));
            //Color trend column
            $(this).children("td:eq("+(index+1)+")").addClass(getColorcode(-trend, trendthres, -trendthres));
        });
    });
}

function updateTable() {
    colorTable();

    $(".tablesorter > tbody")
        //Add permalink events to table rows
        .on("click", "tr", function() {
            var environment = $("input[name='environment']:checked").val();
            permalinkToTimeline($(this).children("td:eq(0)").text(), environment);
        })
        //Add hover effect to rows
        .on("mouseenter mouseleave", "tr", function() {
            $(this).toggleClass("highlight");
        });

    //Configure table as tablesorter
    $(".tablesorter").tablesorter({widgets: ['zebra']});

    // Set prev and next links
    $("#previous").click(function() {
        refreshContentRev(
            $("#previous").data("revision"),
            $("#previous").data("desc")
        );
    });
    $("#next").click(function() {
        refreshContentRev(
            $("#next").data("revision"),
            $("#next").data("desc")
        );
    });
}

function updateRevisionMarkers(env_id) {
    var has = {};
    $.each(envhasresults[env_id] || [], function(_, commitid) { has[commitid] = true; });
    var current = $("#revision").val();
    var options = "";
    $.each(revisiondata[currentproject] || [], function(_, r) {
        var marker = has[r[1]] ? '● ' : '○ ';
        options += "<option value='" + r[1] + "'>" + marker + r[0] + "</option>";
    });
    $("#revision").html(options);
    $("#revision").val(current);
    if (!$("#revision").val()) {
        $("#revision").prop('selectedIndex', 0);
    }
}

function refreshContent() {
    refreshContentTable($("#revision option:selected").val());
}

function refreshContentRev(revision, desc) {
    if ($('#revision option[value='+revision+']').length == 0) {
        $("#revision").append($("<option value='" + revision + "'>" + desc + "</option>"));
    }
    $("#revision").val(revision);
    refreshContentTable(revision);
}

function refreshContentTable(revision) {
    var h = $("#content").height();//get height for loading text
    $("#contentwrap").fadeOut("fast", function() {
        $(this).show();
        $(this).html(getLoadText("Loading...", h));
        $(this).load("table/", $.param(getConfiguration(revision)), function() { updateTable(); });
    });
}

function changeRevisions() {
    // This function repopulates the revision selectbox everytime a new
    // executable is selected that corresponds to a different project.
    var executable = $("input[name='executable']:checked").val(),
        selected_project = projectmatrix[executable];

    if (selected_project !== currentproject) {
        var oldRevs = revisiondata[currentproject] || [];
        var oldEntry = oldRevs.find(function(r) { return r[1] === $("#revision").val(); });
        var oldDate = oldEntry ? new Date(oldEntry[0].slice(0, 19)) : null;
        currentproject = selected_project;
        updateRevisionMarkers($("input[name='environment']:checked").val());
        if (oldDate) {
            var newRevs = revisiondata[currentproject] || [];
            var best = newRevs.reduce(function(bi, r, i) {
                return Math.abs(new Date(r[0].slice(0, 19)) - oldDate) <
                       Math.abs(new Date(newRevs[bi][0].slice(0, 19)) - oldDate) ? i : bi;
            }, 0);
            $("#revision").prop('selectedIndex', best);
        }

        //Give visual cue that the select box has changed
        var bgc = $("#revision").parent().parent().css("backgroundColor");
        $("#revision").parent()
            .animate({ backgroundColor: "#9DADC6" }, 200, function() {
            // Animation complete.
            $(this).animate({ backgroundColor: bgc }, 1500);
        });
    }
    refreshContent();
}

function config(c) {
    changethres = c.changethres;
    trendthres = c.trendthres;
}

function init(defaults) {
    currentproject = defaults.project;
    projectmatrix = defaults.projectmatrix;
    envhasresults = defaults.envhasresults || {};

    $.each(defaults.revisionlists, function(project, revs) {
        revisiondata[project] = revs;
        var options = "";
        $.each(revs, function(index, r) {
            options += "<option value='" + r[1] + "'>" + r[0] + "</option>";
        });
        revisionboxes[project] = options;
    });

    $("#trend").val(defaults.trend);
    $("#trend").change(refreshContent);

    $("#executable" + defaults.executable).prop('checked', true);
    $("input[name='executable']").change(changeRevisions);

    $("#env" + defaults.environment).prop('checked', true);
    $("input[name='environment']").change(function() {
        updateRevisionMarkers($("input[name='environment']:checked").val());
        refreshContent();
    });

    $("#revision").html(revisionboxes[defaults.project]);
    $("#revision").val(defaults.revision);
    updateRevisionMarkers(defaults.environment);
    $("#revision").change(refreshContent);

    $("#permalink").click(function() {
        window.location = "?" + $.param(getConfiguration());
    });

    refreshContent();
}

return {
    init: init,
    config: config
};

})(window);
