FROM python:3.10-bookworm

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Do this _early_ so that we have the lowest chance of needing to "reseed" the clone
# on every build.
RUN git clone https://github.com/python/cpython.git /srv/data/repos/cpython

# By default, Docker has special steps to avoid keeping APT caches in the layers, which
# is good, but in our case, we're going to mount a special cache volume (kept between
# builds), so we WANT the cache to persist.
RUN set -eux; \
    rm -f /etc/apt/apt.conf.d/docker-clean; \
    echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' > /etc/apt/apt.conf.d/keep-cache;

# Install System level build requirements, this is done before
# everything else because these are rarely ever going to change.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    set -x \
    && apt-get update \
    && apt-get install --no-install-recommends -y \
        build-essential git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

RUN mkdir /srv/src
WORKDIR /srv/src
COPY requirements.txt /srv/src/
COPY deploy-requirements.txt /srv/src/
RUN pip install -r deploy-requirements.txt
COPY . /srv/src/
RUN touch /srv/src/speed_python/local_settings.py
RUN \
  DATABASE_URL=None \
  DJANGO_SECRET_KEY=None \
  DJANGO_SETTINGS_MODULE=speed_python.cabotage_settings \
  python manage.py collectstatic --noinput
