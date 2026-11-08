# Codespeed
[![Tests](https://github.com/python/codespeed/actions/workflows/test.yml/badge.svg?branch=main)](https://github.com/python/codespeed/actions/workflows/test.yml)

Codespeed is a web application to monitor and analyze the performance of your code.

This started as a fork of [tobami/codespeed](https://github.com/tobami/codespeed),
however it is now developed independently here, and has different requirements. 
The `codespeed` Django app is still generic and could possibly be used for other
projects. `speed_python` and `speed_pypy` hold what is specific to the two sites.

For an overview of some application concepts see the original project's
[wiki page](https://github.com/tobami/codespeed/wiki/Overview).

## Installation

You will need Python 3.10 or newer.

Clone this repository and install the dependencies:

    git clone https://github.com/python/codespeed.git
    cd codespeed
    pip install -r requirements.txt

If you want version control integration, there are additional requirements:

* Subversion needs pysvn: `python-svn`
* Mercurial needs the package `mercurial` to clone the repo locally
* git needs the `git` package to clone the repo
* For Github the isodate package is required, but not git: `pip install isodate`

**Note**: For git or mercurial repos, the first time the changes view is accessed,
Codespeed will try to clone the repo, which depending on the size of the project
can take a long time. Please be patient.

* To get started, you can use the `sample_project` directory as a starting point for your Django project, which can be normally configured by editing `sample_project/settings.py`.
* For simplicity, you can use the default sqlite configuration, which will save
  the data to a database named `data.db`
* Create the DB by typing from the root directory:

        python manage.py migrate

* Create an admin user:

        python manage.py createsuperuser

* For testing purposes, you can now start the development server:

        python manage.py runserver 8000

The codespeed installation can now be accessed by navigating to `http://localhost:8000/`.

**Note**: for production, you should configure a real server like Apache or nginx (refer to the [Django docs](http://docs.djangoproject.com/en/dev/howto/deployment/)). You should also
modify `sample_project/settings.py` and set `DEBUG = False`.

### Running the tests

The test suite uses its own site-independent settings module:

        python manage.py test codespeed speed_python speed_pypy --settings=codespeed.tests.settings

## Codespeed configuration

### Using the provided test data

If you want to test drive Codespeed, you can use the testdata.json fixtures to have a working data set to browse.

* From the root directory, type:

        ./manage.py loaddata codespeed/fixtures/testdata.json

### Starting from scratch

Before you can start saving (and displaying) data, you need to first create an
environment and define a default project.

* Go to `http://localhost:8000/admin/codespeed/environment/`
  and create an environment.
* Go to `http://localhost:8000/admin/codespeed/project/`
  and create a project.

Check the field "Track changes" and, in case you want version control
integration, configure the relevant fields.

**Note**: Only executables associated to projects with a checked "track changes"
field will be shown in the Changes and Timeline views.

**Note**: Git and Mercurial need to locally clone the repository. That means that your `sample_project/repos` directory will need to be owned by the server. In the case of a typical Apache installation, you'll need to type `sudo chown www-data:www-data sample_project/repos`

## Saving data

Data is saved POSTing to `http://localhost:8000/result/add/`.

You can use the script `tools/save_single_result.py` as a guide.
When saving large quantities of data, it is recommended to use the JSON API instead:
    `http://localhost:8000/result/add/json/`

An example script is located at `tools/save_multiple_results.py`

**Note**: If the given executable, benchmark, project, or
revision do not yet exist, they will be automatically created, together with the
actual result entry. The only model which won't be created automatically is the
environment. It must always exist or the data won't be saved (that is the reason
it is described as a necessary step in the previous "Codespeed configuration"
section).

## Further customization

### Custom Settings

You may override any of the default settings by setting them in
`sample_project/settings.py`. It is strongly recommended that you only override the
settings you need by importing the default settings and replacing only the
values needed for your customizations:

    from codespeed.settings import *

    DEF_ENVIRONMENT = "Dual Core 64 bits"

### Site-wide Changes

All pages inherit from the `base.html` template. To change every page on the site 
simply edit (`sample_project/templates/codespeed/base_site.html`) and override
the appropriate block:

* Custom title: you may replace the default "My Speed Center" for the title
  block with your prefered value:

        {% block title %}
            My Project's Speed Center
        {% endblock %}

* Replacing logo.svg: Place your logo in `sample_project/static/images/logo.svg`
* Logo with custom filename: Place your logo in `sample_project/static/images/` and add a block like
  this to `base_site.html`:

        {% block logo %}
            <img src="{{ MEDIA_URL }}images/my-logo.jpg" width="120" height="48" alt="My Project">
        {% endblock logo %}

  n.b. the layout will stay exactly the same for any image with a height of
  48px (any width will do)

* Custom JavaScript or CSS: add your files to the `sample_project/static/js` directory
  and extend the `extra_head` template block:

        {% block extra_head %}
            {{ block.super }}
            <script type="text/javascript" src="{{ MEDIA_URL }}static/js/my_cool_tweaks.js">
        {% endblock extra_head %}

### Specific Pages

Since `sample_project/templates/codespeed` is the first entry in `settings.TEMPLATE_DIRS` you
may override any template on the site simply by creating a new one with the
same name.

* About page: create `sample_project/templates/about.html`:

        {% extends "codespeed/base_site.html" %}
        {% block title %}{{ block.super }}: About this project{% endblock %}
        {% block body %}
            <div id="sidebar"></div>
            <div id="about" class="about_content clearfix">
                Your content here
            </div>
        {% endblock %}

### Baselines and Comparison view executables

* The results associated to an executable and a revision which has a non blank
  tag field will be listed as a baseline option in the Timeline view.
* Additionally, the Comparison view will show the results of the latest revision
  of projects being tracked as an executable as well.

### Defaults

The file `sample_project/settings.py` can contain customizations of
several parameters (the file includes comments with full examples).

### General settings

* `WEBSITE_NAME`: The RSS results feed will use this parameter as the site name
* `DEF_BASELINE`: Defines which baseline option will be chosen as default in
  the Timeline and Changes views.
* `DEF_ENVIRONMENT`: Defines which environment should be selected as default
  in the Changes and Timeline views.
* `CHANGE_THRESHOLD`
* `TREND_THRESHOLD`

### Home Page

The main customization for the homepage is to display either the reports
(daily changes) or the historical graphs (improvement over time).

* `SHOW_REPORTS`: If set to `True` displays a table and RSS feed with the latest results
* `SHOW_HISTORICAL`: Displays two graphs comparing tagged and latest versions of the default executable and project to the configured baseline.

  To activate the historical graphs you will need to set the following settings (using values that work with the test data):

  * `DEF_BASELINE = {'executable': 'baseExe', 'revision': '444'}`
  * `DEF_EXECUTABLE = "myexe O3 64bits"`

### Changes View

* `DEF_EXECUTABLE`: in the Changes view, a random executable is chosen as
  default. It that doesn't suite you, you can specify here which one should be
  selected. You need to specify its id (since the name alone is not unique).

### Timeline View

* `DEF_BENCHMARK`: Defines the default timeline view. Possible values:
  * `None`: will show a grid of plot thumbnails, or a text message when the number of plots exceeds 30
  * `grid`: will always show as default the grid of plots
  * `show_none`: will show a text message (better default when there are lots of benchmarks)
  * `mybench`: will select benchmark named "mybench"

### Comparison View

* `CHART_TYPE`: Chooses the default chart type (normal bars, stacked bars or
  relative bars)
* `NORMALIZATION`: Defines whether normalization should be enabled as default
  in the Comparison view.
* `CHART_ORIENTATION`: horizontal or vertical
* `COMP_ENVIRONMENTS_DEFAULT`: `all` (the default) checks every environment;
  `default` checks only `DEF_ENVIRONMENT`, or the first environment.
* `COMP_EXECUTABLES`: per default all executables will be checked. When there
  are a large number of tags or executables, it is better to only select a few
  so that the plots are not too cluttered.
  Given as a list of tuples containing the name of an executable + commitid of a revision. An 'L' denotes the last revision. Example:

```python
COMP_EXECUTABLES = [
    ('myexe', '21df2423ra'),
    ('myexe', 'L'),
]
```
* `COMPARISON_COMMIT_TAGS: Defines a list of tags to display on the comparison page. This comes
  handy when there are a lot of tags. It defaults to ``None`` which means display all the available
  tags.

### VCS Provider Specific Settings

#### Github

* ``GITHUB_OAUTH_TOKEN`` - Github oAuth token to use for authenticating against
  the Github API. If not provided, it will default to unauthenticated API requests
  which have low rate limits so an exception may be thrown when retrieving info
  from the Github API due to the rate limit being reached.

## Getting help and reporting bugs

Questions, suggestions and bug reports for this fork belong on the
[GitHub issue tracker](https://github.com/python/codespeed/issues).
The original project's Google group and issue tracker are no longer active.

## History and license

Codespeed was written by Miquel Torres and contributors (see `AUTHORS`). It is
licensed under the GNU Lesser General Public License v2.1 (see `LICENSE`), this
fork keeps that license.
