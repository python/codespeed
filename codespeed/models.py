# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

import logging
import os
import json

from django.core.exceptions import ValidationError
from django.urls import reverse
from django.conf import settings
from django.db import models

from .commits.github import GITHUB_URL_RE

logger = logging.getLogger(__name__)


class Project(models.Model):
    NO_LOGS = 'N'
    GIT = 'G'
    GITHUB = 'H'
    MERCURIAL = 'M'
    SUBVERSION = 'S'
    REPO_TYPES = (
        (NO_LOGS, 'none'),
        (GIT, 'git'),
        (GITHUB, 'Github.com'),
        (MERCURIAL, 'mercurial'),
        (SUBVERSION, 'subversion'),
    )

    name = models.CharField(unique=True, max_length=30)
    repo_type = models.CharField(
        "Repository type", max_length=1, choices=REPO_TYPES, default=NO_LOGS)
    repo_path = models.CharField("Repository URL", blank=True, max_length=200)
    repo_user = models.CharField("Repository username",
                                 blank=True, max_length=100)
    repo_pass = models.CharField("Repository password",
                                 blank=True, max_length=100)
    commit_browsing_url = models.CharField("Commit browsing URL",
                                           blank=True, max_length=200)
    track = models.BooleanField("Track changes", default=True)
    default_branch = models.CharField(max_length=32)

    def __str__(self):
        return self.name

    @property
    def repo_name(self):
        # name not defined for None, GitHub or Subversion
        if self.repo_type in ('N', 'H', 'S'):
            error = 'Not supported for %s project' % self.get_repo_type_display()
            raise AttributeError(error)

        return os.path.splitext(self.repo_path.split(os.sep)[-1])[0]

    @property
    def working_copy(self):
        # working copy exists for mercurial and git only
        if self.repo_type in ('N', 'H', 'S'):
            error = 'Not supported for %s project' % self.get_repo_type_display()
            raise AttributeError(error)

        return os.path.join(settings.REPOSITORY_BASE_PATH, self.repo_name)

    def save(self, *args, **kwargs):
        """Provide a default for commit browsing url in github repositories."""
        if not self.commit_browsing_url and self.repo_type == self.GITHUB:
            m = GITHUB_URL_RE.match(self.repo_path)
            if m:
                url = 'https://github.com/%s/%s/commit/{commitid}' % (
                    m.group('username'), m.group('project')
                )
                self.commit_browsing_url = url
        super(Project, self).save(*args, **kwargs)


class HistoricalValue(object):
    def __init__(self, name=None, val=0, color='none'):
        self.name = name
        self.val = val
        self.color = color

    def update_if_less_important_than(self, val, color, name):
        if self.is_less_important_than(val, color):
            # Do update biggest total change
            self.val = val
            self.color = color
            self.name = name

    def is_less_important_than(self, val, color):
        if color == "red" and self.color != "red":
            return True
        elif color == "red" and abs(val) > abs(self.val):
            return True
        elif (color == "green" and self.color != "red" and
                abs(val) > abs(self.val)):
            return True
        else:
            return False


class Branch(models.Model):
    name = models.CharField(max_length=32)
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="branches")
    display_on_comparison_page = models.BooleanField(
        "True to display this branch on the comparison page",
        default=True)

    def __str__(self):
        return self.project.name + ":" + self.name

    class Meta:
        unique_together = ("name", "project")
        verbose_name_plural = "branches"


class Revision(models.Model):
    # git and mercurial's SHA-1 length is 40
    commitid = models.CharField(max_length=42)
    tag = models.CharField(max_length=20, blank=True)
    date = models.DateTimeField(null=True)
    message = models.TextField(blank=True)
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="revisions",
        null=True, blank=True)
    author = models.CharField(max_length=100, blank=True)
    branch = models.ForeignKey(
        Branch, on_delete=models.CASCADE, related_name="revisions")

    def get_short_commitid(self):
        return self.commitid[:10]

    def get_browsing_url(self):
        return self.branch.project.commit_browsing_url.format(**self.__dict__)

    def __str__(self):
        if self.date is None:
            date = None
        else:
            date = self.date.isoformat(sep=" ")
        string = " - ".join(filter(None, (date, self.commitid, self.tag)))
        if self.branch.name != self.branch.project.default_branch:
            string += " - " + self.branch.name
        return string

    class Meta:
        unique_together = ("commitid", "branch")

    def clean(self):
        if not self.commitid or self.commitid == "None":
            raise ValidationError("Invalid commit id %s" % self.commitid)
        if self.branch.project.repo_type == "S":
            try:
                int(self.commitid)
            except ValueError:
                raise ValidationError("Invalid SVN commit id %s" % self.commitid)


class Executable(models.Model):
    name = models.CharField(max_length=30)
    description = models.CharField(max_length=200, blank=True)
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="executables")

    class Meta:
        unique_together = ('name', 'project')

    def __str__(self):
        return self.name


class Benchmark(models.Model):
    S_TYPES = (
        ('legacy', 'Legacy'),
        ('pyperformance', 'PyPerformance'),
    )
    D_TYPES = (
        ('U', 'Mean'),
        ('M', 'Median'),
    )

    name = models.CharField(max_length=100)
    parent = models.ForeignKey(
        'self', on_delete=models.CASCADE, verbose_name="parent",
        help_text="allows to group benchmarks in hierarchies",
        null=True, blank=True, default=None)
    source = models.CharField(max_length=14, choices=S_TYPES, default='legacy')
    data_type = models.CharField(max_length=1, choices=D_TYPES, default='U')
    description = models.CharField(max_length=300, blank=True)
    units_title = models.CharField(max_length=30, default='Time')
    units = models.CharField(max_length=20, default='seconds')
    lessisbetter = models.BooleanField("Less is better", default=True)
    default_on_comparison = models.BooleanField(
        "Default on comparison page", default=True)

    class Meta:
        unique_together = (('name', 'source'),)

    def ident(self):
        return "%s.%s" % (self.name, self.source)

    def __str__(self):
        return self.name


class Environment(models.Model):
    name = models.CharField(unique=True, max_length=100)
    cpu = models.CharField(max_length=100, blank=True)
    memory = models.CharField(max_length=100, blank=True)
    os = models.CharField(max_length=100, blank=True)
    kernel = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return self.name


class Result(models.Model):
    value = models.FloatField()
    std_dev = models.FloatField(blank=True, null=True)
    val_min = models.FloatField(blank=True, null=True)
    val_max = models.FloatField(blank=True, null=True)
    q1 = models.FloatField(blank=True, null=True)
    q3 = models.FloatField(blank=True, null=True)
    suite_version = models.CharField(max_length=50, blank=True, default='')
    date = models.DateTimeField(blank=True, null=True)
    revision = models.ForeignKey(
        Revision, on_delete=models.CASCADE, related_name="results")
    executable = models.ForeignKey(
        Executable, on_delete=models.CASCADE, related_name="results")
    benchmark = models.ForeignKey(
        Benchmark, on_delete=models.CASCADE, related_name="results")
    environment = models.ForeignKey(
        Environment, on_delete=models.CASCADE, related_name="results")

    def __str__(self):
        return u"%s: %s" % (self.benchmark.name, self.value)

    class Meta:
        unique_together = ("revision", "executable", "benchmark", "environment")


class Report(models.Model):
    revision = models.ForeignKey(
        Revision, on_delete=models.CASCADE, related_name="reports")
    environment = models.ForeignKey(
        Environment, on_delete=models.CASCADE, related_name="reports")
    executable = models.ForeignKey(
        Executable, on_delete=models.CASCADE, related_name="reports")
    summary = models.CharField(max_length=64, blank=True)
    colorcode = models.CharField(max_length=10, default="none")
    _tablecache = models.TextField(blank=True)

    def __str__(self):
        return u"Report for %s" % self.revision

    class Meta:
        unique_together = ("revision", "executable", "environment")

    def save(self, *args, **kwargs):
        tablelist = self.get_changes_table(force_save=True)
        self.reinitialize()
        changes = self.aggregate_significant_changes(tablelist)
        self.update_to_highest_priority_change(changes)

        super(Report, self).save(*args, **kwargs)

    def update_to_highest_priority_change(self, changes):
        average_change = changes['average_change']
        max_change = changes['max_change']
        average_trend = changes['average_trend']
        max_trend = changes['max_trend']

        # Average change
        if average_change.color != "none":
            self.update_summary("Average {} {}", average_change)
            self.colorcode = average_change.color

        # Single benchmark change
        elif max_change.color != "none":
            self.update_summary("{} {}", max_change)
            self.colorcode = max_change.color

        # Average trend
        elif average_trend.color != "none":
            self.update_summary("Average {} trend {}", average_trend)
            self.update_by_trend_color(average_trend.color)

        # Single benchmark trend
        elif max_trend.color != "none":
            self.update_summary("{} trend {}", max_trend)
            # use lighter colors for trend results:
            self.update_by_trend_color(max_trend.color)

    def reinitialize(self):
        self.summary = ""
        self.colorcode = "none"

    def aggregate_significant_changes(self, tablelist):
        # Get default threshold values
        change_threshold = 3.0
        trend_threshold = 5.0
        if (hasattr(settings, 'CHANGE_THRESHOLD') and
                settings.CHANGE_THRESHOLD is not None):
            change_threshold = settings.CHANGE_THRESHOLD
        if hasattr(settings, 'TREND_THRESHOLD') and settings.TREND_THRESHOLD:
            trend_threshold = settings.TREND_THRESHOLD

        max_change = HistoricalValue()
        max_trend = HistoricalValue()
        average_change = HistoricalValue()
        average_trend = HistoricalValue()

        # Fetch big changes for each quantity and each benchmark
        for quantity in tablelist:
            quantity_name = quantity['units_title'].lower()
            less_is_better = quantity['lessisbetter']

            val = quantity['totals']['change']
            if val == "-":
                continue
            color = self.getcolorcode(val, less_is_better, change_threshold)
            average_change.update_if_less_important_than(val, color,
                                                         quantity_name)

            val = quantity['totals']['trend']
            if val != "-":
                color = self.getcolorcode(val, less_is_better, trend_threshold)
                average_trend.update_if_less_important_than(val, color,
                                                            quantity_name)

            for row in quantity['rows']:
                benchmark_name = row['bench_name']
                # Single change
                val = row['change']
                if val == "-":
                    continue
                color = self.getcolorcode(val, less_is_better,
                                          change_threshold)
                max_change.update_if_less_important_than(val, color,
                                                         benchmark_name)
                # Single trend
                val = row['trend']
                if val == "-":
                    continue
                color = self.getcolorcode(val, less_is_better, trend_threshold)
                max_trend.update_if_less_important_than(val, color,
                                                        benchmark_name)
        return {'max_change': max_change,
                'max_trend': max_trend,
                'average_change': average_change,
                'average_trend': average_trend}

    def update_summary(self, format, hist_value):
        self.summary = format.format(hist_value.name,
                                     self.updown(hist_value.val))

    def updown(self, val):
        """Substitutes plus/minus with up/down"""
        direction = val >= 0 and "up" or "down"
        aval = abs(val)
        if aval == float("inf"):
            return u"%s ∞%%" % direction
        else:
            return "%s %.1f%%" % (direction, aval)

    def update_by_trend_color(self, color):
        # use lighter colors for trend results:
        if color == "red":
            self.colorcode = "yellow"
        elif color == "green":
            self.colorcode = "lightgreen"

    def getcolorcode(self, val, lessisbetter, threshold):
        if lessisbetter:
            val = -val
        if val < -threshold:
            return "red"
        elif val > threshold:
            return "green"
        else:
            return "none"

    def get_last_revisions(self, depth):
        lastrevisions = []
        try:
            lastrevisions = Revision.objects.filter(
                branch=self.revision.branch
            ).filter(
                date__lte=self.revision.date
            ).order_by('-date')[:depth + 1]
            # Same as self.revision unless in a different branch
        except Exception as e:
            logger.warning("Exception while getting results: %s", e,
                           exc_info=True)
        return lastrevisions

    def get_changes_table(self, trend_depth=10, force_save=False):
        # Determine whether required trend value is the default one
        default_trend = 10
        if hasattr(settings, 'TREND') and settings.TREND:
            default_trend = settings.TREND
        # If the trend is the default and a forced save is not required
        # just return the cached changes table
        if not force_save and trend_depth == default_trend:
            return self._get_tablecache()
        # Otherwise generate a new changes table
        # Get latest revisions for this branch (which also sets the project)
        lastrevisions = list(self.get_last_revisions(trend_depth))
        if not lastrevisions:
            return []

        changerevision = None
        pastrevisions = []
        if len(lastrevisions) > 1:
            changerevision = lastrevisions[1]
            pastrevisions = lastrevisions[trend_depth - 2:trend_depth + 1]

        # Bulk fetch all results needed across current, change, and past revisions
        relevant_revs = [lastrevisions[0]]
        if changerevision:
            relevant_revs.append(changerevision)
        relevant_revs.extend(pastrevisions)
        results_map = {
            (r.revision_id, r.benchmark_id): r
            for r in Result.objects.filter(
                revision__in=relevant_revs,
                environment=self.environment,
                executable=self.executable,
            )
        }

        # Fetch and group all benchmarks in one query, preserving DB order
        benchmarks_by_units = {}
        for bench in Benchmark.objects.all():
            benchmarks_by_units.setdefault(bench.units_title, []).append(bench)

        current_rev_id = lastrevisions[0].pk
        change_rev_id = changerevision.pk if changerevision else None
        past_rev_ids = [rev.pk for rev in pastrevisions]

        tablelist = []
        for units_title, bench_group in benchmarks_by_units.items():
            currentlist = []
            units = ""
            hasmin = False
            hasmax = False
            has_stddev = False
            smallest = 1000
            totals = {'change': [], 'trend': []}
            for bench in bench_group:
                units = bench.units
                lessisbetter = bench.lessisbetter

                resobj = results_map.get((current_rev_id, bench.pk))
                if resobj is None:
                    continue

                std_dev = resobj.std_dev
                if std_dev is not None:
                    has_stddev = True
                else:
                    std_dev = "-"

                val_min = resobj.val_min
                if val_min is not None:
                    hasmin = True
                else:
                    val_min = "-"

                val_max = resobj.val_max
                if val_max is not None:
                    hasmax = True
                else:
                    val_max = "-"

                # Calculate percentage change relative to previous result
                result = max(resobj.value, 0)
                change = "-"
                if change_rev_id is not None:
                    c = results_map.get((change_rev_id, bench.pk))
                    if c is not None:
                        if c.value != 0:
                            change = (result - c.value) * 100 / c.value
                            totals['change'].append(result / c.value)
                        elif c.value == 0:
                            if result == 0:
                                # 0/0 = 1, in our world
                                change = 0
                                totals['change'].append(1)
                            else:
                                # n/0 = ∞
                                change = float("inf")
                                totals['change'].append(float("inf"))

                # Calculate trend:
                # percentage change relative to average of 3 previous results
                result_sum = 0
                num_past_results = 0
                for rev_id in past_rev_ids:
                    past_r = results_map.get((rev_id, bench.pk))
                    if past_r is not None:
                        result_sum += past_r.value
                        num_past_results += 1
                trend = "-"
                if result_sum:
                    average = result_sum / num_past_results
                    trend = (result - average) * 100 / average
                    totals['trend'].append(result / average)

                # Retain lowest number different than 0
                # to be used later for calculating significant digits
                if result < smallest and result:
                    smallest = result

                currentlist.append({
                    'bench_name': bench.name,
                    'bench_source': bench.source,
                    'bench_description': bench.description,
                    'result': result,
                    'std_dev': std_dev,
                    'val_min': val_min,
                    'val_max': val_max,
                    'change': change,
                    'trend': trend
                })

            # Compute Arithmetic averages
            for key in totals.keys():
                if len(totals[key]):
                    totals[key] = float(sum(totals[key]) / len(totals[key]))
                else:
                    totals[key] = "-"

            if totals['change'] != "-":
                # Transform ratio to percentage
                totals['change'] = (totals['change'] - 1) * 100
            if totals['trend'] != "-":
                # Transform ratio to percentage
                totals['trend'] = (totals['trend'] - 1) * 100

            # Calculate significant digits
            digits = 2
            while smallest < 1:
                smallest *= 10
                digits += 1

            tablelist.append({
                'units': units,
                'units_title': units_title,
                'lessisbetter': lessisbetter,
                'has_stddev': has_stddev,
                'hasmin': hasmin,
                'hasmax': hasmax,
                'precission': digits,
                'totals': totals,
                'rows': currentlist
            })
        if force_save:
            self._save_tablecache(tablelist)
        return tablelist

    def get_absolute_url(self):
        return reverse("changes") + "?rev=%s&exe=%s&env=%s" % (
            self.revision.commitid, self.executable.id, self.environment.name)

    def item_description(self):
        if self.summary == "":
            return "no significant changes"
        else:
            return self.summary

    def _save_tablecache(self, data):
        self._tablecache = json.dumps(data)

    def _get_tablecache(self):
        if self._tablecache == '':
            return {}
        return json.loads(self._tablecache)
